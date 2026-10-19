# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the tiered health probe and its audience resolver.

Covers: KAL-API-004, KAL-SEC-001
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta import __version__
from kaleta.api import create_api_router
from kaleta.api.deps import get_public_session
from kaleta.api.errors import register_error_handlers
from kaleta.api.v1 import health as health_module
from kaleta.api.v1.health import HealthAudience, health_audience, register_health_alias
from kaleta.config import settings
from kaleta.services.health_service import HealthService
from kaleta.services.nicegui_storage_service import NiceguiStorageService
from tests.conftest import make_session_factory

_ADMIN_FIELDS = {"tenants_pending_migration", "keyring_sessions", "suspended_tenants"}


def _probe_app(db_engine, audience: HealthAudience | None) -> FastAPI:
    """A bare app serving the health routes, with the probe's session (and tier) pinned."""
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_api_router())
    register_health_alias(app)

    factory = make_session_factory(db_engine)

    async def override_session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_public_session] = override_session
    if audience is not None:
        app.dependency_overrides[health_audience] = lambda: audience
    return app


# ── Route: tier → body ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_probe_is_liveness_only(db_engine) -> None:
    """No credentials resolve to the public tier: liveness only.

    Covers: KAL-API-004, KAL-SEC-001
    """
    app = _probe_app(db_engine, audience=None)  # the real resolver sees no creds -> public
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "database_ok": True}


@pytest.mark.asyncio
async def test_alias_public_probe_is_liveness_only(db_engine) -> None:
    """Covers: KAL-API-004 — /health alias, public tier"""
    app = _probe_app(db_engine, audience=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database_ok"] is True
    assert "version" not in body


@pytest.mark.asyncio
async def test_family_tier_adds_version_but_no_cross_family_state(db_engine) -> None:
    """A signed-in family caller sees the version (KAL-OPS-001) but no cross-family state.

    Covers: KAL-SEC-001, KAL-OPS-001
    """
    app = _probe_app(db_engine, audience="family")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/v1/health")).json()
    assert body["version"] == __version__
    assert body["auth_backend"] == "local"
    assert isinstance(body["migrations_pending"], bool)
    for field in _ADMIN_FIELDS:
        assert field not in body


@pytest.mark.asyncio
async def test_admin_tier_reports_backend_and_keyring_count(db_engine) -> None:
    """Covers: KAL-API-004, KAL-SEC-001 — the administrative fields"""
    from kaleta.crypto import DataKey, key_ring

    app = _probe_app(db_engine, audience="admin")
    before = key_ring.count()
    key_ring.put("health-probe-session", DataKey(dek=b"\x01" * 32), member_ref="u:1")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/v1/health")).json()
    finally:
        key_ring.lock("health-probe-session")

    assert body["version"] == __version__
    assert body["auth_backend"] == "local"
    assert body["keyring_sessions"] == before + 1
    assert body["suspended_tenants"] == []
    assert body["tenants_pending_migration"] == 0


# ── Audience resolver ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bearer_env_token_is_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The KALETA_API_TOKEN env token is the instance administrator → admin tier.

    Covers: KAL-SEC-001
    """
    monkeypatch.setattr(settings, "api_token", "env-token-long-enough-1234567890")
    assert await health_module._bearer_audience("env-token-long-enough-1234567890") == "admin"


@pytest.mark.asyncio
async def test_bearer_garbage_token_is_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unparseable bearer never promotes the caller — a probe must not 401.

    Covers: KAL-SEC-001
    """
    monkeypatch.setattr(settings, "api_token", None)
    assert await health_module._bearer_audience("not-a-real-token") == "public"


@pytest.mark.asyncio
async def test_audience_falls_back_to_public_when_resolution_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing tier lookup degrades to public — a probe answers 200/503, not 500.

    The case that matters: a credential arrives while the database is down. The
    resolver must not propagate, or ``_health_payload`` never gets to map an
    unreachable database to 503.

    Covers: KAL-SEC-001
    """

    async def _boom(_token):
        raise RuntimeError("database down")

    monkeypatch.setattr(health_module, "_bearer_audience", _boom)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="kt_1_xxxxxxxxxxxxxxxx")
    assert await health_audience(object(), creds) == "public"  # type: ignore[arg-type]


def _patch_family_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake only the DB seams so a ``kt_`` token authenticates as a family member."""
    from kaleta.models.tenant import TenantStatus

    monkeypatch.setattr(settings, "api_token", None)

    class _FakeTenant:
        id = 7
        schema_name = "t_0123456789ab"
        status = TenantStatus.ACTIVE

    class _Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_a):
            return False

    class _FakeFactory:
        @staticmethod
        def public():
            return _Ctx()

        def __call__(self):
            return _Ctx()

    class _FakeTenantService:
        def __init__(self, _session):
            pass

        async def get_tenant(self, _tenant_id):
            return _FakeTenant()

    class _FakeTokenService:
        def __init__(self, _session):
            pass

        @staticmethod
        def tenant_id_from_token(_token):
            return 7

        async def authenticate_bearer(self, _token):
            return 42  # a member id → the token authenticates

    monkeypatch.setattr(health_module, "AsyncSessionFactory", _FakeFactory())
    monkeypatch.setattr(health_module, "TenantService", _FakeTenantService)
    monkeypatch.setattr(health_module, "ApiTokenService", _FakeTokenService)
    monkeypatch.setattr(health_module, "set_tenant", lambda _ctx: None)


@pytest.mark.asyncio
async def test_family_bearer_through_the_real_resolver_hides_cross_family_state(
    db_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end through the real resolver: a family token stops at the family tier.

    The route is wired to the real ``health_audience`` (only the DB seams are
    faked), so this exercises the resolver, the service and serialisation
    together. A family-scoped credential — whoever owns it, instance admin
    included — never reaches the admin tier, so another family's suspended ids
    and cross-family counts stay hidden.

    Covers: KAL-SEC-001
    """
    _patch_family_bearer(monkeypatch)
    app = _probe_app(db_engine, audience=None)  # real resolver, not an override
    headers = {"Authorization": "Bearer kt_7_xxxxxxxxxxxxxxxx"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == __version__  # the family tier was reached
    assert body["auth_backend"] == "local"
    for field in _ADMIN_FIELDS:
        assert field not in body, f"a family token must not see {field}"


@pytest.mark.asyncio
async def test_cookie_without_session_is_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers: KAL-SEC-001"""

    async def _no_user(_request):
        return None

    monkeypatch.setattr(health_module, "authenticated_user_id", _no_user)
    assert await health_module._cookie_audience(object()) == "public"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cookie_admin_is_admin_but_non_admin_is_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cookie session is admin only when the registry confirms it — not the nav hint.

    Covers: KAL-SEC-001
    """
    from dataclasses import dataclass

    @dataclass
    class _FakeTenant:
        auth_subject: str = "local:1"
        email: str = "owner@example.test"

    async def _a_user(_request):
        return 1

    def _a_tenant():
        return _FakeTenant()

    monkeypatch.setattr(health_module, "authenticated_user_id", _a_user)
    monkeypatch.setattr(health_module, "session_tenant", _a_tenant)

    async def _is_admin(*_args, **_kwargs):
        return True

    monkeypatch.setattr(health_module, "is_instance_admin", _is_admin)
    assert await health_module._cookie_audience(object()) == "admin"  # type: ignore[arg-type]

    async def _not_admin(*_args, **_kwargs):
        return False

    monkeypatch.setattr(health_module, "is_instance_admin", _not_admin)
    assert await health_module._cookie_audience(object()) == "family"  # type: ignore[arg-type]


# ── Service: disclosure tiers ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_public_tier_does_no_registry_reads(session: AsyncSession) -> None:
    """The public tier fills liveness only; everything else stays None.

    Covers: KAL-SEC-001
    """
    snap = await HealthService(session).check(include_family=False, include_admin=False)
    assert snap.status == "ok"
    assert snap.database_ok is True
    assert snap.version is None
    assert snap.auth_backend is None
    assert snap.migrations_pending is None
    assert snap.tenants_pending_migration is None
    assert snap.keyring_sessions is None
    assert snap.suspended_tenants is None


@pytest.mark.asyncio
async def test_service_family_tier_withholds_admin_fields(session: AsyncSession) -> None:
    """Covers: KAL-SEC-001"""
    snap = await HealthService(session).check(include_family=True, include_admin=False)
    assert snap.version == __version__
    assert snap.auth_backend is not None
    assert snap.migrations_pending is False
    # Admin-only fields stay None at the family tier.
    assert snap.tenants_pending_migration is None
    assert snap.keyring_sessions is None
    assert snap.suspended_tenants is None


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
            snap = await HealthService(public).check(include_family=True, include_admin=True)
    assert snap.database_ok is True
    assert snap.migrations_pending is True
    assert snap.tenants_pending_migration == 1
    assert snap.version == __version__
    assert snap.version != "0.1.0"


@pytest.mark.asyncio
async def test_health_service_reports_not_pending_when_at_head(session: AsyncSession) -> None:
    """The suite's registry and family are migrated to head: nothing is pending."""
    snap = await HealthService(session).check(include_family=True, include_admin=True)
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
            snap = await HealthService(public).check(include_family=True, include_admin=True)

    assert snap.auth_backend == "supabase"
    assert snap.suspended_tenants == [first.id]
