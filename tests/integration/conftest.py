# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration test fixtures — an ASGI client in the suite family, one transaction per test."""

from __future__ import annotations

from typing import Any

import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from kaleta.api import create_api_router
from kaleta.api.deps import (
    get_public_session,
    get_session,
    resolve_request_tenant,
)
from kaleta.api.errors import register_error_handlers
from kaleta.config import settings
from kaleta.crypto import key_ring, tenant_member_ref
from kaleta.db.tenant_context import use_tenant
from kaleta.models.user import User
from kaleta.services.api_token_service import ApiTokenService
from tests.conftest import SUITE_FAMILY, TEST_DATA_KEY, make_session_factory

ACCOUNT_PAYLOAD: dict[str, Any] = {
    "name": "Main Checking",
    "type": "checking",
    "balance": "100.00",
    "currency": "PLN",
}

INSTITUTION_PAYLOAD: dict[str, Any] = {"name": "Test Bank", "type": "bank"}

CATEGORY_PAYLOAD: dict[str, Any] = {"name": "Food", "type": "expense"}

PAYEE_PAYLOAD: dict[str, Any] = {"name": "Grocery Store"}


@pytest_asyncio.fixture
async def api_user(db_engine):
    """The suite family's owner, whose bearer token the API tests use."""
    factory = make_session_factory(db_engine)
    async with factory() as session:
        user = await session.get(User, SUITE_FAMILY.member_user_id)
    assert user is not None
    if settings.encryption_enabled:
        # A bearer token rides on its member's unlocked browser session; stand
        # one in, so the 423 path stays the real one for everyone else.
        member_ref = tenant_member_ref(SUITE_FAMILY.tenant_id, user.id)
        key_ring.put("api-test-browser", TEST_DATA_KEY, member_ref=member_ref)
    return user


@pytest_asyncio.fixture
async def api_bearer_token(db_engine, api_user):
    """Raw bearer token (``kt_<family>_…``) for integration API calls."""
    factory = make_session_factory(db_engine)
    with use_tenant(SUITE_FAMILY):
        async with factory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=api_user.id,
                label="integration-test",
            )
    return raw


@pytest_asyncio.fixture
async def api_client(db_engine, api_bearer_token):
    """AsyncClient wired to a fresh FastAPI app that uses the test DB engine."""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())

    factory = make_session_factory(db_engine)

    async def override_session(_tenant: None = Depends(resolve_request_tenant)):
        # Still behind the tenant resolution the real dependency runs.
        async with factory() as s:
            yield s

    async def override_public_session():
        # The registry rides on the test's connection too: registry models
        # name `public` themselves, so the translate map leaves them be.
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_public_session] = override_public_session

    headers = {"Authorization": f"Bearer {api_bearer_token}"}
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers=headers,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def api_client_unauth(db_engine):
    """API client without authentication headers."""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())

    factory = make_session_factory(db_engine)

    async def override_session(_tenant: None = Depends(resolve_request_tenant)):
        # Still behind the tenant resolution the real dependency runs.
        async with factory() as s:
            yield s

    async def override_public_session():
        # The registry rides on the test's connection too: registry models
        # name `public` themselves, so the translate map leaves them be.
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_public_session] = override_public_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def create_account(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/accounts/", json={**ACCOUNT_PAYLOAD, **overrides})
    assert resp.status_code == 201
    return resp.json()


async def create_institution(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/institutions/", json={**INSTITUTION_PAYLOAD, **overrides})
    assert resp.status_code == 201
    return resp.json()


async def create_category(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/categories/", json={**CATEGORY_PAYLOAD, **overrides})
    assert resp.status_code == 201
    return resp.json()


async def create_payee(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    resp = await client.post("/api/v1/payees/", json={**PAYEE_PAYLOAD, **overrides})
    assert resp.status_code == 201
    return resp.json()


def transaction_payload(account_id: int, category_id: int, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "account_id": account_id,
        "category_id": category_id,
        "amount": "50.00",
        "type": "expense",
        "date": "2026-01-15",
        "description": "test transaction",
    }
    base.update(overrides)
    return base


def budget_payload(category_id: int, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "category_id": category_id,
        "amount": "500.00",
        "month": 1,
        "year": 2026,
    }
    base.update(overrides)
    return base
