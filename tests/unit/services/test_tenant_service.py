# SPDX-License-Identifier: AGPL-3.0-or-later
"""TenantService — the hosted registry and provisioning (ADR-35).

Covers: KAL-TEN-001
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.db.tenant_schemas import is_valid_schema_name
from kaleta.exceptions import ConflictError, UnauthorizedError
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus, TenantRole, TenantStatus
from kaleta.models.user import User
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, identity, multi_tenant_database


@pytest.fixture
async def hosted(tmp_path: Path):
    async with multi_tenant_database(tmp_path) as url:
        yield url


async def _count(model: type) -> int:
    async with AsyncSessionFactory.public() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_first_verified_sign_in_provisions_schema_owner_and_user(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        tenant = await TenantService(public, provisioner=provisioner).provision(identity(1))
        membership = await TenantService(public).get_member_by_subject(identity(1).subject)

    assert is_valid_schema_name(tenant.schema_name)
    assert tenant.schema_name.startswith("t_")
    assert "member1" not in tenant.schema_name
    assert tenant.status is TenantStatus.ACTIVE
    assert provisioner.created == [tenant.schema_name]
    assert membership is not None
    assert membership.member.role is TenantRole.OWNER
    assert membership.member.status is TenantMemberStatus.ACTIVE
    assert membership.member.email == "member1@example.com"
    assert membership.member.user_id is not None

    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            users = (await session.execute(select(User))).scalars().all()
    assert [(u.username, u.email, u.password_hash) for u in users] == [
        ("member1@example.com", "member1@example.com", None)
    ]
    assert users[0].id == membership.member.user_id


async def test_provisioning_twice_returns_the_same_tenant(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        first = await service.provision(identity(1))
        second = await service.provision(identity(1))

    assert first.id == second.id
    assert provisioner.created == [first.schema_name]
    assert await _count(Tenant) == 1
    assert await _count(TenantMember) == 1


async def test_a_double_submitted_sign_in_creates_one_schema(hosted: str) -> None:
    """Covers: KAL-TEN-001 — two sign-ins racing each other, each on its own session."""
    provisioner = MetadataProvisioner(hosted)

    async def _sign_in() -> int:
        async with AsyncSessionFactory.public() as public:
            tenant = await TenantService(public, provisioner=provisioner).provision(identity(1))
            return tenant.id

    ids = await asyncio.gather(_sign_in(), _sign_in())

    assert ids[0] == ids[1]
    assert len(provisioner.created) == 1
    assert await _count(Tenant) == 1


async def test_an_unverified_identity_gets_no_account(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        with pytest.raises(UnauthorizedError):
            await TenantService(public, provisioner=provisioner).provision(
                identity(1, verified=False)
            )

    assert provisioner.created == []
    assert await _count(Tenant) == 0


async def test_an_email_already_in_the_registry_is_refused(hosted: str) -> None:
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        await service.provision(identity(1, email="shared@example.com"))
        with pytest.raises(ConflictError):
            await service.provision(identity(2, email="Shared@Example.com"))

    assert await _count(Tenant) == 1


async def test_a_crash_mid_provisioning_is_resumed_not_duplicated(hosted: str) -> None:
    """Covers: KAL-TEN-001"""
    provisioner = MetadataProvisioner(hosted, fail_first=True)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await service.provision(identity(1))
        half = await service.get_member_by_subject(identity(1).subject)
        assert half is not None
        assert half.tenant.status is TenantStatus.PROVISIONING

        tenant = await service.provision(identity(1))

    assert tenant.id == half.tenant.id
    assert tenant.schema_name == half.tenant.schema_name
    assert tenant.status is TenantStatus.ACTIVE
    assert await _count(Tenant) == 1


async def test_sign_in_to_a_suspended_account_is_refused(hosted: str) -> None:
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        tenant = await service.provision(identity(1))
        await service.suspend(tenant.id)
        with pytest.raises(UnauthorizedError):
            await service.membership_for_sign_in(identity(1))


async def test_an_email_changed_at_the_provider_follows_into_both_rows(hosted: str) -> None:
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        await service.provision(identity(1))
        membership = await service.membership_for_sign_in(
            identity(1, email="New.Address@Example.com")
        )

    assert membership.member.email == "new.address@example.com"
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            user = await session.get(User, membership.member.user_id)
    assert user is not None
    assert (user.email, user.username) == ("new.address@example.com", "new.address@example.com")


async def test_deleting_a_tenant_drops_its_schema_and_rows(hosted: str) -> None:
    """The schema goes with the account."""
    provisioner = MetadataProvisioner(hosted)
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=provisioner)
        tenant = await service.provision(identity(1))
        schema = tenant.schema_name
        subjects = await service.delete(tenant.id)

    assert subjects == [identity(1).subject]
    assert provisioner.dropped == [schema]
    assert await _count(Tenant) == 0
    assert await _count(TenantMember) == 0
