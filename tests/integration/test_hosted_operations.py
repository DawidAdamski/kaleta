# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operating a hosted instance: startup migration, the admin script, the debug backend.

Covers: KAL-TEN-008, KAL-TEN-010, KAL-TEN-011, KAL-TEN-014
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from kaleta.auth.providers import FakeAuthProvider, Identity
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import UnauthorizedError
from kaleta.models.tenant import Tenant, TenantStatus
from kaleta.services import setup_service
from kaleta.services.health_service import HealthService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database

# Slow tier (test-suite-speed): operator scripts in subprocesses, tenant migrations.
pytestmark = pytest.mark.slow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TENANT_ADMIN = PROJECT_ROOT / "scripts" / "tenant_admin.py"


@pytest.fixture
async def hosted(tmp_path: Path) -> AsyncIterator[str]:
    async with multi_tenant_database() as url:
        yield url


async def _status(tenant_id: int) -> TenantStatus | None:
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, tenant_id)
        return tenant.status if tenant is not None else None


async def test_a_tenant_that_fails_to_migrate_is_suspended_and_the_rest_start(
    hosted: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers: KAL-TEN-010"""
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=MetadataProvisioner(hosted))
        broken = await service.provision(identity(1))
        healthy = await service.provision(identity(2))
        broken_schema, healthy_schema = broken.schema_name, healthy.schema_name
    # Built from metadata, neither schema carries an alembic revision: both
    # count as behind head, and startup tries to migrate both.
    upgraded: list[str] = []

    def _upgrade(db_url: str, *, schema: str | None = None) -> None:
        if schema == broken_schema:
            msg = "relation already exists"
            raise RuntimeError(msg)
        upgraded.append(str(schema))

    monkeypatch.setattr(setup_service, "upgrade_to_head", _upgrade)

    run = setup_service.ensure_multi_tenant_current(hosted)

    assert run.suspended == [broken_schema]
    assert run.migrated == [healthy_schema]
    assert upgraded == [healthy_schema]
    assert await _status(broken.id) is TenantStatus.SUSPENDED
    assert await _status(healthy.id) is TenantStatus.ACTIVE
    async with AsyncSessionFactory.public() as public:
        snapshot = await HealthService(public).check()
        assert snapshot.suspended_tenants == [broken.id]
        tenants = TenantService(public, provisioner=MetadataProvisioner(hosted))
        with pytest.raises(UnauthorizedError):
            await tenants.membership_for_sign_in(identity(1))
        membership = await tenants.membership_for_sign_in(identity(2))
        assert membership.tenant.id == healthy.id


async def test_the_fake_backend_signs_up_and_provisions_an_account(
    hosted: str, tmp_path: Path
) -> None:
    """Covers: KAL-TEN-011"""
    provider = FakeAuthProvider(tmp_path / "fake-auth.json")

    result = await provider.sign_up("ania@example.com", "correct-horse-battery")
    assert result.identity is not None
    async with AsyncSessionFactory.public() as public:
        tenants = TenantService(public, provisioner=MetadataProvisioner(hosted))
        membership = await tenants.membership_for_sign_in(result.identity)

    assert membership.tenant.status is TenantStatus.ACTIVE
    assert membership.tenant.schema_name.startswith("t_")
    assert membership.member.email == "ania@example.com"
    again = await provider.sign_in("ania@example.com", "correct-horse-battery")
    assert isinstance(again, Identity)
    async with AsyncSessionFactory.public() as public:
        same = await TenantService(public).get_member_by_subject(again.subject)
    assert same is not None
    assert same.tenant.id == membership.tenant.id


def _tenant_admin(db_url: str, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TENANT_ADMIN), *args],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "KALETA_DB_URL": db_url,
            "KALETA_TENANCY": "multi",
            "KALETA_AUTH_BACKEND": "fake",
            "KALETA_DEBUG": "true",
        },
        check=False,
        capture_output=True,
        text=True,
    )


async def test_the_operator_lists_suspends_and_deletes_an_account(
    hosted: str, tmp_path: Path
) -> None:
    """Covers: KAL-TEN-008"""
    home = tmp_path / "home"
    provider = FakeAuthProvider(home / ".kaleta" / "fake-auth.json")
    signed_up = await provider.sign_up("ania@example.com", "correct-horse-battery")
    assert signed_up.identity is not None
    async with AsyncSessionFactory.public() as public:
        tenant = await TenantService(public, provisioner=MetadataProvisioner(hosted)).provision(
            signed_up.identity
        )
        tenant_id = tenant.id

    listed = _tenant_admin(hosted, home, "list")
    assert listed.returncode == 0, listed.stderr
    row = listed.stdout.splitlines()[1].split()
    assert row[:4] == [str(tenant_id), tenant.schema_name, "active", "1"]

    members = _tenant_admin(hosted, home, "members", str(tenant_id))
    assert members.stdout.splitlines() == ["ania@example.com\towner\tactive"]

    assert _tenant_admin(hosted, home, "suspend", str(tenant_id)).returncode == 0
    assert await _status(tenant_id) is TenantStatus.SUSPENDED

    refused = _tenant_admin(hosted, home, "delete", str(tenant_id))
    assert refused.returncode == 1
    assert await _status(tenant_id) is TenantStatus.SUSPENDED

    deleted = _tenant_admin(hosted, home, "delete", str(tenant_id), "--yes")
    assert deleted.returncode == 0, deleted.stderr
    audit = json.loads(deleted.stdout)
    assert audit["event"] == "tenant_deleted"
    assert audit["tenant_id"] == tenant_id
    assert audit["identities_removed"] == 1
    assert await _status(tenant_id) is None
    with pytest.raises(UnauthorizedError):
        await provider.sign_in("ania@example.com", "correct-horse-battery")


RESET_DEMO = PROJECT_ROOT / "scripts" / "reset_demo.py"


def _reset_demo(db_url: str, home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RESET_DEMO), "--force", *args],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(home),
            "KALETA_DB_URL": db_url,
            "KALETA_TENANCY": "multi",
            "KALETA_AUTH_BACKEND": "fake",
            "KALETA_DEBUG": "true",
        },
        check=False,
        capture_output=True,
        text=True,
    )


async def test_the_hosted_demo_is_provisioned_once_and_reset_in_place(
    hosted: str, tmp_path: Path
) -> None:
    """Covers: KAL-TEN-014"""
    home = tmp_path / "home"

    first = _reset_demo(hosted, home, "--tenant", "demo")
    assert first.returncode == 0, first.stderr + first.stdout
    assert "Demo data passphrase set up." in first.stdout
    second = _reset_demo(hosted, home, "--tenant", "demo")
    assert second.returncode == 0, second.stderr + second.stdout
    assert "Demo data passphrase set up." not in second.stdout

    demo = await FakeAuthProvider(home / ".kaleta" / "fake-auth.json").sign_in(
        "demo@kaleta.app", "demo-kaleta"
    )
    assert isinstance(demo, Identity)
    async with AsyncSessionFactory.public() as public:
        tenants = await TenantService(public).list_tenants()
        owner = await TenantService(public).get_member_by_subject(demo.subject)
    assert len(tenants) == 1
    assert owner is not None
    assert owner.tenant.id == tenants[0].id
    assert f"account {tenants[0].id}" in second.stdout
    seeded = re.search(r"(\d+) transactions", second.stdout)
    assert seeded is not None
    assert int(seeded.group(1)) > 0


def test_reset_demo_refuses_tenant_on_a_single_tenant_install(tmp_path: Path) -> None:
    """Covers: KAL-TEN-014"""
    result = subprocess.run(
        [sys.executable, str(RESET_DEMO), "--force", "--tenant", "demo"],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "KALETA_DB_URL": f"sqlite+aiosqlite:///{tmp_path / 'single.db'}",
            "KALETA_TENANCY": "single",
            "KALETA_AUTH_BACKEND": "local",
            "KALETA_DEBUG": "true",
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "--tenant goes with KALETA_TENANCY=multi" in result.stderr


async def test_only_the_active_owner_of_that_account_may_delete_it(hosted: str) -> None:
    """Covers: KAL-TEN-009 — the owner check behind Settings → Data."""
    from kaleta.services.account_deletion_service import AccountDeletionService

    class _NoRemover:
        async def delete_identity(self, subject: str) -> None:
            raise AssertionError("nothing may be removed here")

    async with AsyncSessionFactory.public() as public:
        tenants = TenantService(public, provisioner=MetadataProvisioner(hosted))
        first = await tenants.provision(identity(1))
        second = await tenants.provision(identity(2))
        service = AccountDeletionService(public, _NoRemover())

        assert await service.is_owner(first.id, identity(1).subject) is True
        assert await service.is_owner(first.id, identity(2).subject) is False
        assert await service.is_owner(second.id, identity(1).subject) is False
        assert await service.is_owner(first.id, "no-such-subject") is False
        members = await service.members(first.id)
    assert [(m.email, m.is_owner) for m in members] == [("member1@example.com", True)]
