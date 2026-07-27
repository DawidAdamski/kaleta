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


def is_authenticated() -> bool:
    return bool(app.storage.user.get(SESSION_AUTHENTICATED, False))


def login_session(*, user_id: int, username: str) -> None:
    app.storage.user[SESSION_AUTHENTICATED] = True
    app.storage.user[SESSION_USER_ID] = user_id
    app.storage.user[SESSION_USERNAME] = username
    app.storage.user[SESSION_LOGIN_AT] = datetime.now(UTC).isoformat()


def logout_session() -> None:
    for key in (SESSION_AUTHENTICATED, SESSION_USER_ID, SESSION_USERNAME, SESSION_LOGIN_AT):
        app.storage.user.pop(key, None)


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
