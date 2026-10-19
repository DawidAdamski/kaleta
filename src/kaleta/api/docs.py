# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAPI schema and Swagger UI, gated by a flag (KAL-SEC-002, assessment F-2).

The schema and the Swagger page at ``/api-docs`` map the whole API surface. They
are served only when ``settings.api_docs_enabled`` says so — which follows
``debug`` unless ``KALETA_API_DOCS`` overrides it — so a production-shaped run
does not hand the surface map to every unauthenticated client. The API routes
and their authentication are unaffected either way.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from kaleta.api import create_api_router
from kaleta.config import settings

# Cached OpenAPI spec — generated once from our router tree.
_openapi_spec: dict[str, Any] | None = None


def build_api_spec() -> dict[str, Any]:
    """The OpenAPI document for the public API, generated once and cached."""
    global _openapi_spec
    if _openapi_spec is None:
        tmp = FastAPI(
            title="Kaleta API",
            version="1.0.0",
            description="Public REST API for the Kaleta personal finance app.",
        )
        tmp.include_router(create_api_router())
        _openapi_spec = tmp.openapi()
    return _openapi_spec


def mount_api_docs(app: FastAPI) -> bool:
    """Mount ``/api-docs`` + ``/api-docs/openapi.json`` when the flag allows it.

    Returns whether the docs were mounted. When gated off, **both** routes are
    absent (404) — the JSON is the schema and must not leak while the HTML page
    is hidden.
    """
    if not settings.api_docs_enabled:
        return False

    @app.get("/api-docs", response_class=HTMLResponse, include_in_schema=False)
    async def _swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api-docs/openapi.json",
            title="Kaleta API",
        )

    @app.get("/api-docs/openapi.json", include_in_schema=False)
    async def _openapi_json() -> dict[str, Any]:
        return build_api_spec()

    return True
