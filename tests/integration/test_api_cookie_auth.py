# SPDX-License-Identifier: AGPL-3.0-or-later
"""API auth: cookie read-only vs bearer for mutations."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api import create_api_router
from kaleta.api.deps import get_session
from kaleta.api.errors import register_error_handlers
from kaleta.services.auth_service import AuthService
from tests.conftest import make_session_factory
from tests.integration.conftest import ACCOUNT_PAYLOAD


@pytest_asyncio.fixture
async def cookie_user(db_engine):
    factory = make_session_factory(db_engine)
    async with factory() as session:
        return await AuthService(session).create_user("cookie-user", "password-123")


@pytest_asyncio.fixture
async def api_app_cookie(db_engine, cookie_user, monkeypatch: pytest.MonkeyPatch):
    """App where session cookie auth resolves to cookie_user for safe methods."""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    factory = make_session_factory(db_engine)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session

    def _uid_from_request(_request: Any) -> int | None:
        return cookie_user.id

    monkeypatch.setattr("kaleta.api.deps.user_id_from_request", _uid_from_request)
    return app


@pytest.mark.asyncio
async def test_cookie_auth_allows_get(api_app_cookie) -> None:
    """Covers: KAL-AUTH-010"""
    async with AsyncClient(
        transport=ASGITransport(app=api_app_cookie),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/accounts/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cookie_auth_rejects_post(api_app_cookie) -> None:
    """Covers: KAL-AUTH-010"""
    async with AsyncClient(
        transport=ASGITransport(app=api_app_cookie),
        base_url="http://test",
    ) as client:
        resp = await client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_bearer_still_allows_post(api_client) -> None:
    """Covers: KAL-AUTH-010"""
    resp = await api_client.post("/api/v1/accounts/", json=ACCOUNT_PAYLOAD)
    assert resp.status_code == 201
