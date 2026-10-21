# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stamp security response headers on every web response.

A pure-ASGI middleware (like :class:`kaleta.logging_config.RequestContextMiddleware`)
that sets a NiceGUI/Vue-safe set of hardening headers on the
``http.response.start`` of every HTTP response — the fix for security
assessment **F-8** (the ZAP baseline found none were set). Registered last in
``run_web`` so it is the outermost middleware and stamps every response,
including the redirects ``AuthMiddleware`` returns.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import MutableHeaders

from kaleta.config import settings

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

# A Content-Security-Policy tuned to what NiceGUI/Vue actually needs. The app
# injects inline <script>/<style> (service-worker registration, theme CSS,
# dashboard bootstrap) and talks to the server over a Socket.IO websocket, so
# 'unsafe-inline'/'unsafe-eval' on script/style and ws:/wss: on connect-src are
# required — tightening them would break the UI (see the plan's CSP notes).
_CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' ws: wss:",
    "img-src 'self' data:",
    "font-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
)
_CSP = "; ".join(_CSP_DIRECTIVES)

# Powerful browser features the app never uses — denied outright.
_PERMISSIONS_POLICY = ", ".join(
    f"{feature}=()"
    for feature in (
        "accelerometer",
        "camera",
        "geolocation",
        "gyroscope",
        "magnetometer",
        "microphone",
        "payment",
        "usb",
    )
)

# Static headers set on every response regardless of configuration.
_STATIC_HEADERS: tuple[tuple[str, str], ...] = (
    ("content-security-policy", _CSP),
    ("x-frame-options", "DENY"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", _PERMISSIONS_POLICY),
    # The Spectre site-isolation set (ZAP 90004). It was deferred from the first
    # F-8 pass on a (mis-attributed) report that CORP broke NiceGUI's
    # websocket-driven MFA navigation; a 2026-10-21 re-investigation under a real
    # browser proved the whole set safe — the websocket, the service worker and
    # the login → /login/mfa hop all work, and the MFA e2e passes with it on.
    # COEP require-corp blocks nothing because the app loads only same-origin
    # subresources (the CSP already pins default-src 'self') and every response
    # here carries CORP. See the F-8 writeup in
    # docs/security/assessment-2026-10-12.md.
    ("cross-origin-opener-policy", "same-origin"),
    ("cross-origin-embedder-policy", "require-corp"),
    ("cross-origin-resource-policy", "same-origin"),
)


class SecurityHeadersMiddleware:
    """Set the hardening response headers on every HTTP response."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _STATIC_HEADERS:
                    headers[name] = value
                # HSTS only behind TLS. session_cookie_secure is the existing
                # signal that the deployment terminates https (F-3), so a
                # legitimate plain-http-behind-proxy / localhost install — which
                # the project supports — is never told to force https.
                if settings.session_cookie_secure:
                    headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_wrapper)
