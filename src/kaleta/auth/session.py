# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-side session state stored in NiceGUI ``app.storage.user``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nicegui import app
from starlette.requests import Request

from kaleta.config import settings

#: How long a password-accepted session may sit in front of the code prompt.
#: Here rather than beside the service's step-up window: it is a fact about a
#: session, and importing the service for it would pull pyotp, qrcode and
#: cryptography into every module that wants to ask who is logged in.
MFA_CHALLENGE_TTL_MINUTES = 10

SESSION_AUTHENTICATED = "authenticated"
SESSION_USER_ID = "user_id"
SESSION_USERNAME = "username"
SESSION_LOGIN_AT = "login_at"

#: A password was accepted but the second factor has not been given yet. The
#: session deliberately carries no ``SESSION_AUTHENTICATED`` while this is set,
#: so every guard in the app — UI middleware and the API cookie path alike —
#: sees a pending session as no session at all.
SESSION_MFA_PENDING = "mfa_pending"
SESSION_MFA_PENDING_USER_ID = "mfa_pending_user_id"
SESSION_MFA_PENDING_USERNAME = "mfa_pending_username"
SESSION_MFA_PENDING_AT = "mfa_pending_at"
#: When the second factor was last proved, for step-up on sensitive actions.
SESSION_MFA_VERIFIED_AT = "mfa_verified_at"

_MFA_PENDING_KEYS = (
    SESSION_MFA_PENDING,
    SESSION_MFA_PENDING_USER_ID,
    SESSION_MFA_PENDING_USERNAME,
    SESSION_MFA_PENDING_AT,
)


def is_authenticated() -> bool:
    return bool(app.storage.user.get(SESSION_AUTHENTICATED, False))


def login_session(*, user_id: int, username: str) -> None:
    # A finished login leaves no half-finished one behind it — and no
    # step-up stamp either. Every path that un-authenticates today goes
    # through `logout_session()`, which pops it, so this is belt and braces;
    # it is also the asymmetry a future "switch user" would quietly turn
    # into a free ten-minute step-up window on somebody else's session.
    clear_mfa_challenge()
    app.storage.user.pop(SESSION_MFA_VERIFIED_AT, None)
    app.storage.user[SESSION_AUTHENTICATED] = True
    app.storage.user[SESSION_USER_ID] = user_id
    app.storage.user[SESSION_USERNAME] = username
    app.storage.user[SESSION_LOGIN_AT] = datetime.now(UTC).isoformat()


def logout_session() -> None:
    for key in (
        SESSION_AUTHENTICATED,
        SESSION_USER_ID,
        SESSION_USERNAME,
        SESSION_LOGIN_AT,
        SESSION_MFA_VERIFIED_AT,
        *_MFA_PENDING_KEYS,
    ):
        app.storage.user.pop(key, None)


def begin_mfa_challenge(*, user_id: int, username: str) -> None:
    """Park a password-authenticated user in front of the code prompt."""
    clear_mfa_challenge()
    app.storage.user[SESSION_MFA_PENDING] = True
    app.storage.user[SESSION_MFA_PENDING_USER_ID] = user_id
    app.storage.user[SESSION_MFA_PENDING_USERNAME] = username
    app.storage.user[SESSION_MFA_PENDING_AT] = datetime.now(UTC).isoformat()


def clear_mfa_challenge() -> None:
    for key in _MFA_PENDING_KEYS:
        app.storage.user.pop(key, None)


def is_mfa_pending() -> bool:
    return bool(app.storage.user.get(SESSION_MFA_PENDING, False))


def mfa_pending_user() -> tuple[int, str] | None:
    """The user waiting on a code, or ``None`` when nobody is.

    A challenge goes stale. Someone who gives the right password and walks
    away leaves a browser that needs only the code; after
    ``MFA_CHALLENGE_TTL_MINUTES`` the password has to be given again.
    """
    if not is_mfa_pending():
        return None
    if not _within(app.storage.user.get(SESSION_MFA_PENDING_AT), MFA_CHALLENGE_TTL_MINUTES):
        clear_mfa_challenge()
        return None
    # A half-written challenge is cleared, exactly like a stale one. Leaving
    # it would keep `is_mfa_pending()` True forever, and `/login/mfa` reads
    # that as "this one expired" — so the page would bounce to
    # `?reason=mfa_expired` on every visit until a full login or logout
    # rewrote the keys.
    raw_id = app.storage.user.get(SESSION_MFA_PENDING_USER_ID)
    username = app.storage.user.get(SESSION_MFA_PENDING_USERNAME)
    if raw_id is None or username is None:
        clear_mfa_challenge()
        return None
    try:
        return int(raw_id), str(username)
    except (TypeError, ValueError):
        clear_mfa_challenge()
        return None


def mark_mfa_verified() -> None:
    app.storage.user[SESSION_MFA_VERIFIED_AT] = datetime.now(UTC).isoformat()


def mfa_verified_at() -> datetime | None:
    """When the second factor was last proved in this session, if ever.

    Services are handed this rather than a boolean: whether it is recent
    enough is ``MfaService``'s judgement, not the session helper's.
    """
    return _stamp(app.storage.user.get(SESSION_MFA_VERIFIED_AT))


def _stamp(raw: object) -> datetime | None:
    if raw is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _within(raw: object, minutes: int) -> bool:
    stamp = _stamp(raw)
    if stamp is None:
        return False
    return datetime.now(UTC) - stamp <= timedelta(minutes=minutes)


def clear_session() -> None:
    """Remove all session keys (alias for logout)."""
    logout_session()


def session_expired() -> bool:
    """True when session TTL is enabled and the login timestamp is too old."""
    ttl_hours = settings.session_ttl_hours
    if ttl_hours <= 0:
        return False
    raw = app.storage.user.get(SESSION_LOGIN_AT)
    if raw is None:
        # Legacy sessions without a stamp — treat as expired so TTL applies.
        return True
    try:
        login_at = datetime.fromisoformat(str(raw))
    except ValueError:
        return True
    if login_at.tzinfo is None:
        login_at = login_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - login_at > timedelta(hours=ttl_hours)


def user_id_from_request(request: Request) -> int | None:
    """Read authenticated user id from the NiceGUI session cookie, if present."""
    try:
        from nicegui.storage import request_contextvar

        request_contextvar.set(request)
        if not app.storage.user.get(SESSION_AUTHENTICATED, False):
            return None
        if session_expired():
            logout_session()
            return None
        raw_id = app.storage.user.get(SESSION_USER_ID)
        return int(raw_id) if raw_id is not None else None
    except (RuntimeError, KeyError, AssertionError, TypeError, ValueError):
        return None
