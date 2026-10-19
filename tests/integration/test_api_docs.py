# SPDX-License-Identifier: AGPL-3.0-or-later
"""The OpenAPI docs are gated by a flag, so a production run does not leak them.

Covers: KAL-SEC-002
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api.docs import mount_api_docs
from kaleta.config import settings


async def _probe(path: str) -> tuple[bool, int]:
    """Mount the docs under the current settings and GET ``path``; (mounted, status)."""
    app = FastAPI()
    mounted = mount_api_docs(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(path)
    return mounted, resp.status_code


async def test_docs_are_absent_in_a_production_shaped_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Debug off and ``api_docs`` unset: both doc routes are 404.

    This is the F-2 fix — the old code mounted ``/api-docs`` and
    ``/api-docs/openapi.json`` unconditionally, so this fails on the old route.

    Covers: KAL-SEC-002
    """
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "api_docs", None)
    assert settings.api_docs_enabled is False

    mounted_page, page_status = await _probe("/api-docs")
    assert mounted_page is False
    assert page_status == 404
    # The JSON is the schema itself and must not leak while the page is hidden.
    _, json_status = await _probe("/api-docs/openapi.json")
    assert json_status == 404


async def test_docs_can_be_published_on_a_production_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """``KALETA_API_DOCS=true`` opts a non-debug instance back into the docs.

    Covers: KAL-SEC-002
    """
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "api_docs", True)
    assert settings.api_docs_enabled is True

    app = FastAPI()
    assert mount_api_docs(app) is True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        page = await client.get("/api-docs")
        spec = await client.get("/api-docs/openapi.json")
    assert page.status_code == 200
    assert "swagger-ui" in page.text.lower()
    assert spec.status_code == 200
    body = spec.json()
    # A real OpenAPI document — version marker and the path map.
    assert body["openapi"].startswith("3.")
    assert "paths" in body


async def test_docs_follow_debug_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``api_docs`` unset, debug on serves the docs as before.

    Covers: KAL-SEC-002
    """
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "api_docs", None)
    assert settings.api_docs_enabled is True

    mounted, status = await _probe("/api-docs")
    assert mounted is True
    assert status == 200


async def test_api_docs_false_overrides_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """``api_docs=False`` keeps the docs off even in debug.

    Covers: KAL-SEC-002
    """
    monkeypatch.setattr(settings, "debug", True)
    monkeypatch.setattr(settings, "api_docs", False)
    assert settings.api_docs_enabled is False

    mounted, status = await _probe("/api-docs")
    assert mounted is False
    assert status == 404
