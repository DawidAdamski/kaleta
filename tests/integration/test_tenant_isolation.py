# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two hosted accounts, one database: each sees only its own rows (ADR-35).

Runs the real provisioning — ``CREATE SCHEMA`` (a file, on SQLite) and every
tenant migration through ``alembic/`` — then drives the public REST API with
each tenant's bearer token. On SQLite by default; against real PostgreSQL
schemas when ``KALETA_DB_URL`` is a PostgreSQL URL (the CI ``postgres-multi``
job).

Covers: KAL-TEN-001, KAL-TEN-002, KAL-TEN-003, KAL-TEN-004
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from kaleta.api import create_api_router
from kaleta.api.deps import require_api_auth, resolve_request_tenant
from kaleta.api.errors import register_error_handlers
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, TenantContextMissingError, use_tenant
from kaleta.models.account import Account
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.backup_service import BackupService
from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService
from tests.tenancy_helpers import identity, multi_tenant_database

#: Written into tenant A's rows only. Tenant B must never see it anywhere.
MARKER_A = "ALPHA-ONLY-7f3c"
MARKER_B = "BRAVO-ONLY-19ad"

#: GET collections whose absence of the other tenant's marker is asserted.
CORE_LISTS = (
    "/api/v1/accounts/",
    "/api/v1/institutions/",
    "/api/v1/categories/",
    "/api/v1/payees/",
    "/api/v1/transactions/",
)


@pytest.fixture(autouse=True)
def _api_assumes_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the integration conftest's patch: multi mode is configured by itself."""
    monkeypatch.setattr("kaleta.api.deps.is_configured", lambda: True)


@dataclass
class Household:
    ctx: TenantContext
    token: str
    client: AsyncClient


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    return app


async def _household(url: str, n: int, app: FastAPI) -> Household:
    async with AsyncSessionFactory.public() as public:
        service = TenantService(
            public, provisioner=AlembicSchemaProvisioner(url, AsyncSessionFactory.public)
        )
        await service.provision(identity(n))
        membership = await service.get_member_by_subject(identity(n).subject)
    assert membership is not None
    ctx = membership.context()
    assert ctx.member_user_id is not None
    with use_tenant(ctx):
        async with AsyncSessionFactory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=ctx.member_user_id, label=f"tenant {n}"
            )
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {raw}"},
    )
    return Household(ctx=ctx, token=raw, client=client)


@pytest.fixture
async def two_households(tmp_path: Path) -> AsyncIterator[tuple[Household, Household]]:
    async with multi_tenant_database(tmp_path) as url:
        app = _app()
        a = await _household(url, 1, app)
        b = await _household(url, 2, app)
        try:
            yield a, b
        finally:
            await a.client.aclose()
            await b.client.aclose()


async def _seed(client: AsyncClient, marker: str, balance: str) -> dict[str, Any]:
    institution = await client.post(
        "/api/v1/institutions/", json={"name": f"Bank {marker}", "type": "bank"}
    )
    assert institution.status_code == 201, institution.text
    account = await client.post(
        "/api/v1/accounts/",
        json={"name": "Main Checking", "type": "checking", "balance": balance, "currency": "PLN"},
    )
    assert account.status_code == 201, account.text
    category = await client.post(
        "/api/v1/categories/", json={"name": f"Food {marker}", "type": "expense"}
    )
    assert category.status_code == 201, category.text
    payee = await client.post("/api/v1/payees/", json={"name": f"Shop {marker}"})
    assert payee.status_code == 201, payee.text
    transaction = await client.post(
        "/api/v1/transactions/",
        json={
            "account_id": account.json()["id"],
            "amount": "12.34",
            "type": "expense",
            "date": "2026-09-01",
            "description": f"Groceries {marker}",
            "category_id": category.json()["id"],
            "payee_id": payee.json()["id"],
        },
    )
    assert transaction.status_code == 201, transaction.text
    return account.json()


def _collection_gets(app: FastAPI) -> list[str]:
    """Every parameterless GET under /api/v1 — every router's list or summary view.

    Read from the OpenAPI document: it is the complete, flattened route list
    (``app.routes`` keeps included routers nested).
    """
    return sorted(
        path
        for path, operations in app.openapi()["paths"].items()
        if "get" in operations and path.startswith("/api/v1/") and "{" not in path
    )


async def test_same_account_name_each_tenant_sees_only_its_own(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-002"""
    a, b = two_households
    account_a = await _seed(a.client, MARKER_A, "100.00")
    account_b = await _seed(b.client, MARKER_B, "250.00")

    # Opening balance less the one 12.34 expense each seed books.
    for client, own_balance in ((a.client, "87.66"), (b.client, "237.66")):
        listed = await client.get("/api/v1/accounts/")
        assert listed.status_code == 200
        accounts = listed.json()
        assert [x["name"] for x in accounts] == ["Main Checking"]
        assert Decimal(accounts[0]["balance"]) == Decimal(own_balance)

    # Same id in both schemas: each token reaches its own row behind it.
    assert account_a["id"] == account_b["id"]
    by_id_b = await b.client.get(f"/api/v1/accounts/{account_a['id']}")
    assert by_id_b.status_code == 200
    assert Decimal(by_id_b.json()["balance"]) == Decimal("237.66")


async def test_no_router_shows_one_tenant_the_other_tenants_rows(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-002 — every parameterless GET of every api/v1 router."""
    a, b = two_households
    await _seed(a.client, MARKER_A, "100.00")
    await _seed(b.client, MARKER_B, "250.00")

    app = _app()
    paths = _collection_gets(app)
    assert set(CORE_LISTS) <= set(paths)
    for path in paths:
        for own, other, other_marker in ((a, b, MARKER_B), (b, a, MARKER_A)):
            response = await own.client.get(path)
            assert response.status_code < 500, (path, response.text)
            assert other_marker not in response.text, (path, other.ctx.schema)
    # The negative check above is only worth something if the lists carry the
    # marker at all. Accounts are named alike on purpose; the rest are not.
    for path in CORE_LISTS:
        mine = await a.client.get(path)
        assert mine.status_code == 200, (path, mine.text)
        if path != "/api/v1/accounts/":
            assert MARKER_A in mine.text, path


async def test_new_rows_are_attributed_to_the_token_owner(
    two_households: tuple[Household, Household],
) -> None:
    a, _b = two_households
    created = await _seed(a.client, MARKER_A, "100.00")
    with use_tenant(a.ctx):
        async with AsyncSessionFactory() as session:
            owner = (
                await session.execute(select(Account.user_id).where(Account.id == created["id"]))
            ).scalar_one()
    assert owner == a.ctx.member_user_id


async def test_a_request_without_tenant_context_fails_closed(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-003 — a route that skipped tenant resolution gets a 500, not data."""
    a, _b = two_households
    await _seed(a.client, MARKER_A, "100.00")

    app = _app()

    async def _forgot_the_tenant() -> None:
        return None

    app.dependency_overrides[resolve_request_tenant] = _forgot_the_tenant
    app.dependency_overrides[require_api_auth] = lambda: 1
    # ASGITransport runs the app in this test's own task, so the tenant the
    # seeding requests resolved is still set here; a server gives every
    # request a fresh context. Start this one with none, as a server would.
    with use_tenant(None):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/accounts/")

    assert response.status_code == 500
    assert MARKER_A not in response.text
    assert "Main Checking" not in response.text
    with use_tenant(None), pytest.raises(TenantContextMissingError):
        AsyncSessionFactory()


async def test_api_token_of_one_tenant_is_rejected_on_the_other(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-004"""
    a, b = two_households
    await _seed(a.client, MARKER_A, "100.00")
    await _seed(b.client, MARKER_B, "250.00")

    secret_a = a.token.split("_", 2)[2]
    forged = f"kt_{b.ctx.tenant_id}_{secret_a}"
    unknown_tenant = f"kt_{a.ctx.tenant_id + b.ctx.tenant_id + 100}_{secret_a}"
    unprefixed = secret_a

    app = _app()
    for token in (forged, unknown_tenant, unprefixed):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.get("/api/v1/accounts/")
        assert response.status_code == 401, (token[:12], response.text)
        assert MARKER_A not in response.text
        assert MARKER_B not in response.text

    # And the real tokens keep working on their own tenants.
    assert (await a.client.get("/api/v1/accounts/")).status_code == 200
    assert (await b.client.get("/api/v1/accounts/")).status_code == 200


async def test_no_credentials_is_unauthorized_not_an_error(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-003"""
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get("/api/v1/accounts/")
    assert response.status_code == 401


async def test_per_account_export_holds_only_that_account(
    two_households: tuple[Household, Household],
) -> None:
    """Covers: KAL-TEN-002 — the Settings → Data export, per tenant."""
    a, b = two_households
    await _seed(a.client, MARKER_A, "100.00")
    await _seed(b.client, MARKER_B, "250.00")

    with use_tenant(a.ctx):
        async with AsyncSessionFactory() as session:
            archive = await BackupService(session).export()
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        dumped = {name: zf.read(name).decode() for name in zf.namelist()}
    assert MARKER_A in dumped["payees.json"]
    assert all(MARKER_B not in content for content in dumped.values())
    assert json.loads(dumped["accounts.json"])[0]["name"] == "Main Checking"
