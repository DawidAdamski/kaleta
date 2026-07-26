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
from kaleta.api.deps import get_session
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

    app.dependency_overrides[get_session] = override_session

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

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json()["database_ok"] is True


@pytest.mark.asyncio
async def test_health_service_reports_pending_when_unstamped(session: AsyncSession) -> None:
    """In-memory create_all DBs have no alembic_version — pending is true."""
    snap = await HealthService(session).check()
    assert snap.database_ok is True
    assert snap.migrations_pending is True
    assert snap.version == "0.1.0"


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
