# SPDX-License-Identifier: AGPL-3.0-or-later
"""Server-side session state stored in NiceGUI ``app.storage.user``."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote
from uuid import uuid4

from nicegui import app, ui
from nicegui.storage import request_contextvar
from starlette.requests import Request

from kaleta.config import settings

if TYPE_CHECKING:
    from kaleta.config.settings import Settings

logger = logging.getLogger(__name__)

#: Our own name rather than Starlette's ``session``, so two NiceGUI apps on one
#: host do not overwrite each other's cookie.
SESSION_COOKIE_NAME = "kaleta_session"

#: How long a password-accepted session may sit in front of the code prompt.
#: Here rather than beside the service's step-up window: it is a fact about a
#: session, and importing the service for it would pull pyotp, qrcode and
#: cryptography into every module that wants to ask who is logged in.
MFA_CHALLENGE_TTL_MINUTES = 10

SESSION_AUTHENTICATED = "authenticated"
SESSION_USER_ID = "user_id"
SESSION_USERNAME = "username"
SESSION_LOGIN_AT = "login_at"
#: When this session last made a request, for the idle timeout.
SESSION_LAST_SEEN_AT = "last_seen_at"

#: ``touch_session()`` rewrites the activity stamp at most this often. Every
#: write to ``app.storage.user`` is a file write, so a busy session costs one
#: per five minutes rather than one per request — and may therefore end up to
#: five minutes before its idle window strictly would.
IDLE_TOUCH_INTERVAL_SECONDS = 300

#: Why ``session_expiry_reason()`` ended a session.
SessionExpiry = Literal["ttl", "idle"]

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

#: Everything that says who this browser is. Whatever is not in here — theme,
#: language, dashboard layout — is a per-browser preference and moves across a
#: rotation; everything in here is dropped by it.
_AUTH_KEYS = (
    SESSION_AUTHENTICATED,
    SESSION_USER_ID,
    SESSION_USERNAME,
    SESSION_LOGIN_AT,
    SESSION_LAST_SEEN_AT,
    SESSION_MFA_VERIFIED_AT,
    *_MFA_PENDING_KEYS,
)


#: The path every finished login and every logout passes through, so that the
#: browser leaves it holding a storage id nobody could have planted beforehand.
SESSION_ROTATE_PATH = "/auth/session/rotate"
#: How long the nonce the handler stamps stays good. The navigation is
#: immediate; this only has to outlast a slow phone.
ROTATE_NONCE_TTL_SECONDS = 60

#: A single-use proof that the navigation to ``SESSION_ROTATE_PATH`` came from
#: the handler that just authenticated (or just signed out) this browser.
SESSION_ROTATE_NONCE = "rotate_nonce"
SESSION_ROTATE_AT = "rotate_at"
#: ``"login"`` or ``"logout"`` — a nonce stamped for one cannot finish the other.
SESSION_ROTATE_PURPOSE = "rotate_purpose"
#: Who the login is for. Parked here rather than written as
#: ``SESSION_AUTHENTICATED``: the id the browser holds before rotation is the
#: one an attacker could have planted, so it is never authenticated at all.
SESSION_ROTATE_USER_ID = "rotate_user_id"
SESSION_ROTATE_USERNAME = "rotate_username"
SESSION_ROTATE_MFA_VERIFIED = "rotate_mfa_verified"

_ROTATE_KEYS = (
    SESSION_ROTATE_NONCE,
    SESSION_ROTATE_AT,
    SESSION_ROTATE_PURPOSE,
    SESSION_ROTATE_USER_ID,
    SESSION_ROTATE_USERNAME,
    SESSION_ROTATE_MFA_VERIFIED,
)

#: Why a nonce was stamped.
RotatePurpose = Literal["login", "logout"]


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
    now = datetime.now(UTC).isoformat()
    app.storage.user[SESSION_LOGIN_AT] = now
    app.storage.user[SESSION_LAST_SEEN_AT] = now


def finish_login(*, user_id: int, username: str, target: str, mfa_verified: bool = False) -> None:
    """End a login handler: park the user, stamp a nonce, go and rotate.

    Runs over the websocket, where no cookie can be set, so the login itself is
    completed by ``SESSION_ROTATE_PATH`` on the HTTP request that follows —
    under a storage id issued there, never under the one the browser came with.
    """
    clear_mfa_challenge()
    nonce = stamp_rotation_nonce("login")
    app.storage.user[SESSION_ROTATE_USER_ID] = user_id
    app.storage.user[SESSION_ROTATE_USERNAME] = username
    app.storage.user[SESSION_ROTATE_MFA_VERIFIED] = mfa_verified
    ui.navigate.to(f"{SESSION_ROTATE_PATH}?nonce={nonce}&redirect_to={quote(target, safe='/')}")


def finish_logout() -> None:
    """End the session now, then send the browser off to get a fresh id."""
    logout_session()
    nonce = stamp_rotation_nonce("logout")
    ui.navigate.to(f"{SESSION_ROTATE_PATH}?nonce={nonce}&logout=1")


def stamp_rotation_nonce(purpose: RotatePurpose) -> str:
    """Store a fresh single-use nonce in the current bucket and return it."""
    for key in _ROTATE_KEYS:
        app.storage.user.pop(key, None)
    nonce = secrets.token_urlsafe(32)
    app.storage.user[SESSION_ROTATE_NONCE] = nonce
    app.storage.user[SESSION_ROTATE_AT] = datetime.now(UTC).isoformat()
    app.storage.user[SESSION_ROTATE_PURPOSE] = purpose
    return nonce


@dataclass(frozen=True)
class PendingRotation:
    """What a consumed nonce was stamped for, read before the bucket is emptied."""

    purpose: RotatePurpose
    user_id: int | None
    username: str | None
    mfa_verified: bool


def consume_rotation_nonce(given: str, purpose: RotatePurpose) -> PendingRotation | None:
    """The rotation ``given`` authorises, or ``None``.

    A matching nonce is spent whatever else is wrong with it, so it cannot be
    replayed. A mismatch leaves the stored one alone: the stored one belongs to
    whoever holds the browser, and a guess at it must not be able to cancel it.
    """
    stored = app.storage.user.get(SESSION_ROTATE_NONCE)
    if not isinstance(stored, str) or not given or not secrets.compare_digest(stored, given):
        return None
    stamped_at = app.storage.user.get(SESSION_ROTATE_AT)
    stored_purpose = app.storage.user.get(SESSION_ROTATE_PURPOSE)
    raw_id = app.storage.user.get(SESSION_ROTATE_USER_ID)
    raw_name = app.storage.user.get(SESSION_ROTATE_USERNAME)
    mfa_verified = bool(app.storage.user.get(SESSION_ROTATE_MFA_VERIFIED, False))
    for key in _ROTATE_KEYS:
        app.storage.user.pop(key, None)
    stamp = _stamp(stamped_at)
    if stamp is None or datetime.now(UTC) - stamp > timedelta(seconds=ROTATE_NONCE_TTL_SECONDS):
        return None
    if stored_purpose != purpose:
        return None
    if purpose == "logout":
        return PendingRotation(purpose, None, None, mfa_verified=False)
    try:
        user_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        user_id = None
    if user_id is None or raw_name is None:
        return None
    return PendingRotation(purpose, user_id, str(raw_name), mfa_verified=mfa_verified)


async def rotate_session_id(request: Request) -> None:
    """Move this browser onto a new storage id, taking its preferences along.

    Relies on how ``nicegui.storage`` resolves ``app.storage.user`` (pinned by
    ``tests/unit/auth/test_session_rotation.py``): ``RequestTrackingMiddleware``
    gives the session its ``request.session["id"]`` and creates that id's
    bucket; every later access looks the bucket up by that key again. So
    setting a new id and creating its bucket switches this request — and, once
    ``SessionMiddleware`` writes the cookie, the browser — to the new bucket.

    The old bucket is emptied, not deleted: its file stays until NiceGUI's own
    sweep, but it no longer says anything about anyone.
    """
    # Normally already this request, set by `RequestTrackingMiddleware`. Set
    # again so that `app.storage.user` below and the `request.session` written
    # below are guaranteed to be the same session whatever the caller.
    request_contextvar.set(request)
    old = app.storage.user
    snapshot = {k: v for k, v in old.items() if k not in _AUTH_KEYS and k not in _ROTATE_KEYS}
    old.clear()
    new_id = str(uuid4())
    await app.storage._create_user_storage(new_id)
    request.session["id"] = new_id
    app.storage.user.update(snapshot)


def touch_session() -> None:
    """Record activity, unless the stamp is younger than the touch interval."""
    last_seen = _stamp(app.storage.user.get(SESSION_LAST_SEEN_AT))
    now = datetime.now(UTC)
    if last_seen is not None and now - last_seen <= timedelta(seconds=IDLE_TOUCH_INTERVAL_SECONDS):
        return
    app.storage.user[SESSION_LAST_SEEN_AT] = now.isoformat()


def logout_session() -> None:
    for key in _AUTH_KEYS:
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
    """True when the session outlived its absolute TTL or its idle window."""
    return session_expiry_reason() is not None


def session_expiry_reason() -> SessionExpiry | None:
    """Which limit ended the session, or ``None`` while it is still good.

    The absolute TTL is checked first: a session past both is a TTL expiry.

    The two rules treat a missing stamp differently, on purpose. A session
    with no login time is expired — the TTL rule bounds how long a stolen
    cookie stays good, and a cookie that cannot say when it was issued must
    not be trusted to be young. A session with no activity time (signed in
    before the idle timeout shipped) is treated as fresh once and stamped
    now: the idle rule only bounds an unattended screen, and a missing
    activity stamp says nothing about whether anyone is sitting at it.
    """
    if _ttl_expired():
        return "ttl"
    if _idle_expired():
        return "idle"
    return None


def _ttl_expired() -> bool:
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


def _idle_expired() -> bool:
    idle_hours = settings.session_idle_hours
    if idle_hours <= 0:
        return False
    now = datetime.now(UTC)
    last_seen = _stamp(app.storage.user.get(SESSION_LAST_SEEN_AT))
    if last_seen is None:
        # Pre-idle-timeout session (or an unreadable stamp): fresh on first
        # sight — see `session_expiry_reason`.
        app.storage.user[SESSION_LAST_SEEN_AT] = now.isoformat()
        return False
    return now - last_seen > timedelta(hours=idle_hours)


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


def session_middleware_kwargs(cfg: Settings | None = None) -> dict[str, str | int | bool]:
    """Keyword arguments for Starlette's ``SessionMiddleware`` (via ``ui.run``).

    The cookie lives exactly as long as the app's own session TTL; with the TTL
    off (``0``) ``max_age`` is left out and Starlette's default applies.
    """
    cfg = cfg if cfg is not None else settings
    kwargs: dict[str, str | int | bool] = {
        "session_cookie": SESSION_COOKIE_NAME,
        "same_site": cfg.session_cookie_samesite,
        "https_only": cfg.session_cookie_secure,
    }
    if cfg.session_ttl_hours > 0:
        kwargs["max_age"] = cfg.session_ttl_hours * 3600
    return kwargs


def warn_secure_cookie_in_debug(cfg: Settings | None = None) -> None:
    """Say so when a debug run marks the cookie ``Secure``.

    That is the combination a developer gets by copying the hosted env file to
    a plain-http ``127.0.0.1``: the browser drops the cookie and login loops.
    """
    cfg = cfg if cfg is not None else settings
    if cfg.session_cookie_secure and cfg.debug:
        logger.warning(
            "KALETA_SESSION_COOKIE_SECURE is on in debug mode: the browser will not "
            "send the session cookie over plain http, so login only works behind TLS."
        )
