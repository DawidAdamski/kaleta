"""Integration test fixtures — ASGI client with in-memory SQLite per test."""

from __future__ import annotations

from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from kaleta.api import create_api_router
from kaleta.api.deps import get_session

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
async def api_client(db_engine):
    """AsyncClient wired to a fresh FastAPI app that uses the test DB engine."""
    app = FastAPI()
    app.include_router(create_api_router())

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_session

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
