# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route guard for NiceGUI UI pages."""

from __future__ import annotations

import logging
from contextlib import suppress
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from kaleta.auth.session import is_authenticated, logout_session, session_expired
from kaleta.config.setup_config import is_configured
from kaleta.services import AuthService, with_session
from kaleta.services.auth_service import AuthState

log = logging.getLogger(__name__)

# Pages reachable without an authenticated session (only when already configured).
_PUBLIC_UI_PATHS: frozenset[str] = frozenset(
    {
        "/login",
        "/create-account",
        "/secure-app",
        "/favicon.ico",
        "/health",
    }
)

# Path prefixes exempt from the auth guard (API uses bearer/session guard in api/deps.py).
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/_nicegui",
    "/static/",
    "/logos/",
    "/api/v1/",
    "/api-docs",
)

_ASSET_PATHS: frozenset[str] = frozenset({"/manifest.json", "/sw.js", "/favicon.ico"})


def is_public_path(path: str) -> bool:
    if path in _PUBLIC_UI_PATHS:
        return True
    if path in _ASSET_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def _is_framework_or_api(path: str) -> bool:
    if path in _ASSET_PATHS or path == "/health":
        return True
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


async def _bootstrap_redirect_path() -> str | None:
    """Return a bootstrap page when the database is not ready for login yet."""

    async def _state(session: AsyncSession) -> AuthState:
        return await AuthService(session).auth_state()

    state = await with_session(_state)
    if state == "no_user":
        return "/create-account"
    if state == "placeholder":
        return "/secure-app"
    return None


def register_auth_middleware() -> None:
    """Install the UI auth guard on the NiceGUI/FastAPI app."""
    from nicegui import app as nicegui_app

    @nicegui_app.add_middleware
    class AuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
            path = request.url.path

            if not is_configured():
                if path == "/setup" or _is_framework_or_api(path):
                    return await call_next(request)
                return RedirectResponse("/setup")

            if is_public_path(path):
                return await call_next(request)

            try:
                authenticated = is_authenticated()
            except RuntimeError:
                log.debug("No NiceGUI client context for %s — treating as unauthenticated", path)
                authenticated = False

            if authenticated:
                try:
                    expired = session_expired()
                except RuntimeError:
                    expired = False
                if expired:
                    with suppress(RuntimeError):
                        logout_session()
                    redirect_to = quote(path, safe="/")
                    return RedirectResponse(f"/login?redirect_to={redirect_to}")
                return await call_next(request)

            try:
                bootstrap = await _bootstrap_redirect_path()
            except Exception:
                log.exception("Auth bootstrap check failed")
                bootstrap = None
            if bootstrap and path != bootstrap:
                return RedirectResponse(bootstrap)

            redirect_to = quote(path, safe="/")
            return RedirectResponse(f"/login?redirect_to={redirect_to}")
