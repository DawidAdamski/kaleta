# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-side session state stored in NiceGUI ``app.storage.user``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nicegui import app
from starlette.requests import Request

from kaleta.config import settings

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
#: When the second factor was last proved, for step-up on sensitive actions.
SESSION_MFA_VERIFIED_AT = "mfa_verified_at"

_MFA_PENDING_KEYS = (
    SESSION_MFA_PENDING,
    SESSION_MFA_PENDING_USER_ID,
    SESSION_MFA_PENDING_USERNAME,
)

#: How long a proved second factor counts as fresh for a sensitive action.
STEP_UP_WINDOW_MINUTES = 10


def is_authenticated() -> bool:
    return bool(app.storage.user.get(SESSION_AUTHENTICATED, False))


def login_session(*, user_id: int, username: str) -> None:
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


def clear_mfa_challenge() -> None:
    for key in _MFA_PENDING_KEYS:
        app.storage.user.pop(key, None)


def is_mfa_pending() -> bool:
    return bool(app.storage.user.get(SESSION_MFA_PENDING, False))


def mfa_pending_user() -> tuple[int, str] | None:
    """The user waiting on a code, or ``None`` when nobody is."""
    if not is_mfa_pending():
        return None
    raw_id = app.storage.user.get(SESSION_MFA_PENDING_USER_ID)
    username = app.storage.user.get(SESSION_MFA_PENDING_USERNAME)
    if raw_id is None or username is None:
        return None
    try:
        return int(raw_id), str(username)
    except (TypeError, ValueError):
        return None


def mark_mfa_verified() -> None:
    app.storage.user[SESSION_MFA_VERIFIED_AT] = datetime.now(UTC).isoformat()


def mfa_recently_verified(*, window_minutes: int = STEP_UP_WINDOW_MINUTES) -> bool:
    """True when the second factor was proved within the step-up window."""
    raw = app.storage.user.get(SESSION_MFA_VERIFIED_AT)
    if raw is None:
        return False
    try:
        verified_at = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return False
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - verified_at <= timedelta(minutes=window_minutes)


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
