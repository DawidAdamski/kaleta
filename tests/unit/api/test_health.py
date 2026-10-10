# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the unauthenticated health probe.

Covers: KAL-API-004
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta import __version__
from kaleta.api import create_api_router
from kaleta.api.deps import get_public_session
from kaleta.api.errors import register_error_handlers
from kaleta.api.v1.health import register_health_alias
from kaleta.services.health_service import HealthService
from kaleta.services.nicegui_storage_service import NiceguiStorageService
from tests.conftest import make_session_factory


@pytest.mark.asyncio
async def test_health_unauthenticated_returns_version_and_db_ok(db_engine) -> None:
    """Covers: KAL-API-004"""
    from fastapi import FastAPI

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    register_health_alias(app)

    factory = make_session_factory(db_engine)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_public_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.1.0"
    assert body["version"] == __version__
    assert body["database_ok"] is True
    assert body["status"] == "ok"
    assert isinstance(body["migrations_pending"], bool)


@pytest.mark.asyncio
async def test_health_alias_unauthenticated(db_engine) -> None:
    """Covers: KAL-API-004 — /health alias"""
    from fastapi import FastAPI

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    register_health_alias(app)

    factory = make_session_factory(db_engine)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_public_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["database_ok"] is True


@pytest.mark.asyncio
async def test_health_service_reports_pending_for_a_family_schema_behind_head() -> None:
    """A family schema with no ``alembic_version`` counts as behind head."""
    from kaleta.db import AsyncSessionFactory
    from kaleta.services.tenant_service import TenantService
    from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database

    async with multi_tenant_database() as url:
        async with AsyncSessionFactory.public() as public:
            # Built from the models, never stamped: what a failed migration leaves.
            await TenantService(public, provisioner=MetadataProvisioner(url)).provision(identity(1))
        async with AsyncSessionFactory.public() as public:
            snap = await HealthService(public).check()
    assert snap.database_ok is True
    assert snap.migrations_pending is True
    assert snap.tenants_pending_migration == 1
    assert snap.version == "0.1.0"


@pytest.mark.asyncio
async def test_health_service_reports_not_pending_when_at_head(session: AsyncSession) -> None:
    """The suite's registry and family are migrated to head: nothing is pending."""
    snap = await HealthService(session).check()
    assert snap.database_ok is True
    assert snap.migrations_pending is False
    assert snap.tenants_pending_migration == 0


def test_nicegui_storage_sweep_removes_stale_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = tmp_path / "nicegui"
    storage.mkdir()
    fresh = storage / "storage-fresh.json"
    stale = storage / "storage-stale.json"
    fresh.write_text("{}", encoding="utf-8")
    stale.write_text("{}", encoding="utf-8")

    # Age the stale file beyond 30 days.
    import os
    import time

    old = time.time() - (31 * 24 * 60 * 60)
    os.utime(stale, (old, old))

    svc = NiceguiStorageService(storage_dir=storage, stale_after_seconds=30 * 24 * 60 * 60)
    removed = svc.sweep_stale()
    assert removed == 1
    assert fresh.is_file()
    assert not stale.exists()


def test_configure_environment_respects_existing_env(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom-nicegui"
    monkeypatch.setenv("NICEGUI_STORAGE_PATH", str(custom))
    path = NiceguiStorageService.configure_environment(tmp_path / "ignored")
    assert path == custom.resolve()
    assert custom.is_dir()


@pytest.mark.asyncio
async def test_health_reports_backend_and_keyring_count(db_engine) -> None:
    """Covers: KAL-API-004 — the operator's fields"""
    from fastapi import FastAPI

    from kaleta.crypto import DataKey, key_ring

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())

    factory = make_session_factory(db_engine)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_public_session] = override_session

    before = key_ring.count()
    key_ring.put("health-probe-session", DataKey(dek=b"\x01" * 32), member_ref="u:1")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/v1/health")).json()
    finally:
        key_ring.lock("health-probe-session")

    assert "tenancy" not in body
    assert body["auth_backend"] == "local"
    assert body["keyring_sessions"] == before + 1
    assert body["suspended_tenants"] == []
    assert body["tenants_pending_migration"] == 0


@pytest.mark.asyncio
async def test_health_lists_suspended_tenants_on_a_hosted_instance(tmp_path) -> None:
    """Covers: KAL-API-004, KAL-TEN-010"""
    from kaleta.db import AsyncSessionFactory
    from kaleta.services.tenant_service import TenantService
    from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database

    async with multi_tenant_database() as url:
        async with AsyncSessionFactory.public() as public:
            service = TenantService(public, provisioner=MetadataProvisioner(url))
            first = await service.provision(identity(1))
            await service.provision(identity(2))
            await service.suspend(first.id)
        async with AsyncSessionFactory.public() as public:
            snap = await HealthService(public).check()

    assert snap.auth_backend == "supabase"
    assert snap.suspended_tenants == [first.id]
