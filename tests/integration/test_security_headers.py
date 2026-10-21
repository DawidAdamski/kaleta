# SPDX-License-Identifier: AGPL-3.0-or-later
"""The web app stamps security response headers on every response.

Covers: KAL-SEC-006 (assessment F-8).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from kaleta.config import settings
from kaleta.security_headers import SecurityHeadersMiddleware

# The headers that must ride on every response, from the BDD literals.
_EXPECTED = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    # The Spectre site-isolation set (ZAP 90004) — shipped after the F-8
    # follow-up investigation found it safe with NiceGUI.
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-embedder-policy": "require-corp",
    "cross-origin-resource-policy": "same-origin",
}


def _app() -> Starlette:
    """A tiny app behind the middleware: an OK route and a redirect route."""

    async def ok(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def redir(_request: Request) -> RedirectResponse:
        return RedirectResponse("/ok")

    app = Starlette(routes=[Route("/ok", ok), Route("/redir", redir)])
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def _client(app: Starlette) -> AsyncClient:
    # follow_redirects stays off so the redirect response itself is inspected.
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_a_normal_response_carries_the_security_headers() -> None:
    """A 200 response carries the CSP, the smaller hardening headers and the
    site-isolation trio (COOP/COEP/CORP).

    Covers: KAL-SEC-006
    """
    async with _client(_app()) as client:
        resp = await client.get("/ok")

    assert resp.status_code == 200
    csp = resp.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp
    # NiceGUI/Vue needs these, so the CSP must keep them.
    assert "script-src 'self' 'unsafe-inline' 'unsafe-eval'" in csp
    assert "connect-src 'self' ws: wss:" in csp
    # Permissions-Policy denies the powerful features the app never uses.
    assert "geolocation=()" in resp.headers["permissions-policy"]
    for name, value in _EXPECTED.items():
        assert resp.headers[name] == value


@pytest.mark.asyncio
async def test_a_redirect_response_carries_them_too() -> None:
    """An auth redirect is stamped as well — the middleware is outermost.

    Covers: KAL-SEC-006
    """
    async with _client(_app()) as client:
        resp = await client.get("/redir")

    assert resp.status_code == 307
    assert "content-security-policy" in resp.headers
    for name, value in _EXPECTED.items():
        assert resp.headers[name] == value


@pytest.mark.asyncio
async def test_hsts_is_sent_only_behind_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strict-Transport-Security rides only when the session cookie is Secure.

    Covers: KAL-SEC-006
    """
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    async with _client(_app()) as client:
        plain = await client.get("/ok")
    assert "strict-transport-security" not in plain.headers

    monkeypatch.setattr(settings, "session_cookie_secure", True)
    async with _client(_app()) as client:
        tls = await client.get("/ok")
    assert tls.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


@pytest.mark.asyncio
async def test_the_toggle_off_skips_the_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    """KALETA_SECURITY_HEADERS_ENABLED=false registers no middleware.

    Covers: KAL-SEC-006
    """
    from kaleta import main

    added: list[object] = []
    monkeypatch.setattr(main.nicegui_app, "add_middleware", lambda cls, **_kw: added.append(cls))

    monkeypatch.setattr(settings, "security_headers_enabled", False)
    main._register_security_headers()
    assert added == []

    monkeypatch.setattr(settings, "security_headers_enabled", True)
    main._register_security_headers()
    assert added == [SecurityHeadersMiddleware]
