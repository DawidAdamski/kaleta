"""Server-side session state stored in NiceGUI ``app.storage.user``."""

from __future__ import annotations

from nicegui import app
from starlette.requests import Request

SESSION_AUTHENTICATED = "authenticated"
SESSION_USER_ID = "user_id"
SESSION_USERNAME = "username"


def is_authenticated() -> bool:
    return bool(app.storage.user.get(SESSION_AUTHENTICATED, False))


def login_session(*, user_id: int, username: str) -> None:
    app.storage.user[SESSION_AUTHENTICATED] = True
    app.storage.user[SESSION_USER_ID] = user_id
    app.storage.user[SESSION_USERNAME] = username


def logout_session() -> None:
    for key in (SESSION_AUTHENTICATED, SESSION_USER_ID, SESSION_USERNAME):
        app.storage.user.pop(key, None)


def clear_session() -> None:
    """Remove all session keys (alias for logout)."""
    logout_session()


def user_id_from_request(request: Request) -> int | None:
    """Read authenticated user id from the NiceGUI session cookie, if present."""
    try:
        from nicegui.storage import request_contextvar

        request_contextvar.set(request)
        if not app.storage.user.get(SESSION_AUTHENTICATED, False):
            return None
        raw_id = app.storage.user.get(SESSION_USER_ID)
        return int(raw_id) if raw_id is not None else None
    except (RuntimeError, KeyError, AssertionError, TypeError, ValueError):
        return None
