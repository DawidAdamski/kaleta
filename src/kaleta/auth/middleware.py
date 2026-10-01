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

from kaleta.auth.session import (
    SESSION_ROTATE_PATH,
    SessionExpiry,
    current_session_revoked,
    is_authenticated,
    logout_session,
    session_expiry_reason,
    session_tenant_context,
    touch_session,
)
from kaleta.config import settings
from kaleta.config.setup_config import is_configured
from kaleta.db.tenant_context import install_tenant_resolver, set_tenant
from kaleta.services import AuthService, with_session
from kaleta.services.auth_service import AuthState

log = logging.getLogger(__name__)

# Pages reachable without an authenticated session (only when already configured).
_PUBLIC_UI_PATHS: frozenset[str] = frozenset(
    {
        "/login",
        "/login/mfa",
        "/create-account",
        "/reset-password",
        "/secure-app",
        # Rotating a session means it is not authenticated under its new id
        # yet; the route checks its own nonce instead.
        SESSION_ROTATE_PATH,
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
    """Return a bootstrap page when the database is not ready for login yet.

    Single-tenant only: a hosted instance has no "first user" — every account
    starts at sign-up — and no tenant to ask before someone has signed in.
    """
    if settings.tenancy == "multi":
        return None

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

    multi = settings.tenancy == "multi"
    if multi:
        # UI event handlers run over the websocket, past this middleware; the
        # resolver gives them the same tenant the page load had.
        install_tenant_resolver(session_tenant_context)

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

            if authenticated and multi:
                ctx = session_tenant_context()
                if ctx is None:
                    # Authenticated but no account: a session from before the
                    # instance went multi-tenant, or a damaged one. Sign it out
                    # rather than serve a page that cannot find its data.
                    with suppress(RuntimeError):
                        logout_session()
                    return RedirectResponse(f"/login?redirect_to={quote(path, safe='/')}")
                set_tenant(ctx)

            if authenticated:
                expiry: SessionExpiry | None
                try:
                    expiry = session_expiry_reason()
                except RuntimeError:
                    expiry = None
                if expiry is not None:
                    with suppress(RuntimeError):
                        logout_session()
                    redirect_to = quote(path, safe="/")
                    reason = "&reason=idle" if expiry == "idle" else ""
                    return RedirectResponse(f"/login?redirect_to={redirect_to}{reason}")
                # Page loads only: `/_nicegui/*` is public above, so an open
                # websocket keeps its current page until the next navigation.
                # The watermark cache bounds how stale this answer can be.
                try:
                    revoked = await current_session_revoked()
                except RuntimeError:
                    revoked = False
                if revoked:
                    with suppress(RuntimeError):
                        logout_session()
                    redirect_to = quote(path, safe="/")
                    return RedirectResponse(
                        f"/login?redirect_to={redirect_to}&reason=signed_out_everywhere"
                    )
                # After the expiry check, never before: a touch first would
                # rescue the very session the idle rule is about to end.
                with suppress(RuntimeError):
                    touch_session()
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
