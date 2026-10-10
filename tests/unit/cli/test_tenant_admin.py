# SPDX-License-Identifier: AGPL-3.0-or-later
"""``kaleta-admin`` — the operator's commands over the registry.

Covers: KAL-TEN-008
"""

from __future__ import annotations

import io
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select

from kaleta.cli import tenant_admin
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import ExternalServiceError
from kaleta.models.tenant import Tenant, TenantMember, TenantStatus
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database


class RecordingRemover:
    """Stands in for the auth provider: remembers whose identity went."""

    def __init__(self, *, fail: bool = False) -> None:
        self.removed: list[str] = []
        self._fail = fail

    async def delete_identity(self, subject: str) -> None:
        if self._fail:
            msg = "Supabase Auth is unreachable"
            raise ExternalServiceError(msg)
        self.removed.append(subject)


@pytest.fixture
async def hosted(tmp_path: Path) -> AsyncIterator[str]:
    async with multi_tenant_database() as url:
        yield url


async def _provision(url: str, n: int) -> int:
    async with AsyncSessionFactory.public() as public:
        tenant = await TenantService(public, provisioner=MetadataProvisioner(url)).provision(
            identity(n)
        )
        return tenant.id


def _cli(remover: RecordingRemover) -> tuple[object, io.StringIO, io.StringIO]:
    out, err = io.StringIO(), io.StringIO()
    cli = tenant_admin.TenantAdminCli(AsyncSessionFactory.public, remover, out=out, err=err)
    return cli, out, err


async def _status(tenant_id: int) -> TenantStatus | None:
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, tenant_id)
        return tenant.status if tenant is not None else None


async def test_list_shows_every_tenant_with_its_member_count(hosted: str) -> None:
    """Covers: KAL-TEN-008"""
    first = await _provision(hosted, 1)
    second = await _provision(hosted, 2)
    cli, out, _err = _cli(RecordingRemover())

    assert await cli.list() == 0

    lines = out.getvalue().splitlines()
    assert lines[0].split() == ["ID", "SCHEMA", "STATUS", "MEMBERS", "LAST", "SEEN"]
    rows = {int(line.split()[0]): line.split() for line in lines[1:]}
    assert set(rows) == {first, second}
    assert rows[first][2] == "active"
    assert rows[first][3] == "1"


async def test_members_lists_email_role_and_status(hosted: str) -> None:
    """Covers: KAL-TEN-008"""
    tenant_id = await _provision(hosted, 1)
    cli, out, _err = _cli(RecordingRemover())

    assert await cli.members(tenant_id) == 0

    assert out.getvalue().splitlines() == ["member1@example.com\towner\tactive"]


async def test_members_of_an_unknown_tenant_is_refused(hosted: str) -> None:
    cli, out, err = _cli(RecordingRemover())

    assert await cli.members(999) == 1

    assert out.getvalue() == ""
    assert "no tenant 999" in err.getvalue()


async def test_suspend_then_resume(hosted: str) -> None:
    """Covers: KAL-TEN-008"""
    tenant_id = await _provision(hosted, 1)
    cli, out, _err = _cli(RecordingRemover())

    assert await cli.suspend(tenant_id) == 0
    assert await _status(tenant_id) is TenantStatus.SUSPENDED
    assert await cli.resume(tenant_id) == 0
    assert await _status(tenant_id) is TenantStatus.ACTIVE
    assert out.getvalue().splitlines() == [
        f"tenant {tenant_id} suspended",
        f"tenant {tenant_id} active",
    ]


async def test_resume_of_an_active_tenant_is_refused(hosted: str) -> None:
    tenant_id = await _provision(hosted, 1)
    cli, _out, err = _cli(RecordingRemover())

    assert await cli.resume(tenant_id) == 1

    assert "not suspended" in err.getvalue()


async def test_delete_needs_yes(hosted: str) -> None:
    tenant_id = await _provision(hosted, 1)
    remover = RecordingRemover()
    cli, _out, err = _cli(remover)

    assert await cli.delete(tenant_id, confirmed=False) == 1

    assert "--yes" in err.getvalue()
    assert remover.removed == []
    assert await _status(tenant_id) is TenantStatus.ACTIVE


async def test_delete_removes_identities_schema_and_rows_and_prints_an_audit_line(
    hosted: str,
) -> None:
    """Covers: KAL-TEN-008"""
    doomed = await _provision(hosted, 1)
    kept = await _provision(hosted, 2)
    remover = RecordingRemover()
    cli, out, _err = _cli(remover)

    assert await cli.delete(doomed, confirmed=True) == 0

    assert remover.removed == [identity(1).subject]
    assert await _status(doomed) is None
    assert await _status(kept) is TenantStatus.ACTIVE
    async with AsyncSessionFactory.public() as public:
        members = (await public.execute(select(TenantMember.email))).scalars().all()
    assert list(members) == ["member2@example.com"]
    audit = json.loads(out.getvalue())
    assert audit["event"] == "tenant_deleted"
    assert audit["tenant_id"] == doomed
    assert audit["identities_removed"] == 1
    assert audit["schema"].startswith("t_")


async def test_delete_stops_before_dropping_anything_when_the_provider_fails(
    hosted: str,
) -> None:
    tenant_id = await _provision(hosted, 1)
    cli, out, err = _cli(RecordingRemover(fail=True))

    assert await cli.delete(tenant_id, confirmed=True) == 1

    assert out.getvalue() == ""
    assert "unreachable" in err.getvalue()
    assert await _status(tenant_id) is TenantStatus.ACTIVE
