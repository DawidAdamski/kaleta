# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one HTTP hop that hands a browser a new session id.

A login or logout handler runs over the websocket, where no cookie can be set.
It stamps a nonce and navigates here; this plain request carries the cookie,
so the new storage id it sets reaches the browser on the redirect.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from kaleta.auth.redirects import safe_redirect
from kaleta.auth.session import (
    SESSION_ROTATE_PATH,
    consume_rotation_nonce,
    login_session,
    mark_mfa_verified,
    rotate_session_id,
)

log = logging.getLogger(__name__)

_SEE_OTHER = 303


def build_session_router() -> APIRouter:
    """The rotation route, as a router the app (or a test app) can include."""
    router = APIRouter()

    @router.get(SESSION_ROTATE_PATH, include_in_schema=False)
    async def rotate_session(
        request: Request, nonce: str = "", redirect_to: str = "/", logout: bool = False
    ) -> RedirectResponse:
        pending = consume_rotation_nonce(nonce, "logout" if logout else "login")
        if pending is None:
            log.info("Session rotation refused: no valid nonce")
            return RedirectResponse("/login", status_code=_SEE_OTHER)
        await rotate_session_id(request)
        if pending.user_id is None or pending.username is None:
            return RedirectResponse("/login", status_code=_SEE_OTHER)
        login_session(user_id=pending.user_id, username=pending.username)
        if pending.mfa_verified:
            mark_mfa_verified()
        return RedirectResponse(safe_redirect(redirect_to), status_code=_SEE_OTHER)

    return router


def register_session_routes() -> None:
    """Mount the rotation route on the NiceGUI/FastAPI app."""
    from nicegui import app as nicegui_app

    nicegui_app.include_router(build_session_router())
