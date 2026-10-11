# SPDX-License-Identifier: AGPL-3.0-or-later
"""InstanceAdminService — what the instance administrator may do (ADR-38 §5).

Covers: KAL-ADM-001, KAL-ADM-002, KAL-ADM-003, KAL-ADM-004, KAL-ADM-005, KAL-ADM-006
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import select

from kaleta.auth.providers import RegistryAuthProvider, set_auth_provider
from kaleta.auth.sign_in import SignedIn, SignInFlow
from kaleta.cli import tenant_admin
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import NotFoundError, UnauthorizedError, ValidationError
from kaleta.models.tenant import AdminAction, AdminAuditEntry, Tenant, TenantStatus
from kaleta.schemas.identity import Identity, RegistrationMode
from kaleta.services import AuthService
from kaleta.services.instance_admin_service import InstanceAdminService
from kaleta.services.local_identity_service import LocalIdentityService
from kaleta.services.tenant_service import TenantService
from tests.tenancy_helpers import MetadataProvisioner, multi_tenant_database

ADMIN = "admin@example.com"
JAN = "jan@example.com"
ANIA = "ania@example.com"
PASSWORD = "correct horse battery"


@pytest.fixture
async def instance(tmp_path: Path) -> AsyncIterator[str]:
    set_auth_provider(RegistryAuthProvider())
    try:
        async with multi_tenant_database(auth_backend="local") as url:
            yield url
    finally:
        set_auth_provider(None)


class _Flow(SignInFlow):
    """SignInFlow with the fast schema builder."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    async def _membership(self, identity: Identity):  # type: ignore[no-untyped-def]
        async with AsyncSessionFactory.public() as public:
            service = TenantService(public, provisioner=MetadataProvisioner(self._url))
            return await service.membership_for_sign_in(identity)


async def _sign_in(url: str, email: str, password: str) -> SignedIn:
    identity = await RegistryAuthProvider().sign_in(email, password)
    assert isinstance(identity, Identity)
    return await _Flow(url).complete(identity)


async def _admin_subject(url: str) -> str:
    """The first sign-up: the instance administrator, with a family of their own."""
    result = await RegistryAuthProvider().sign_up(ADMIN, PASSWORD)
    assert result.identity is not None
    await _Flow(url).complete(result.identity)
    return result.identity.subject


def _service(public, url: str, actor: str | None):  # type: ignore[no-untyped-def]
    return InstanceAdminService(
        public,
        actor=actor,
        auth_backend="local",
        remover=RegistryAuthProvider(),
        provisioner=MetadataProvisioner(url),
    )


async def _create_family(url: str, actor: str, name: str, owner: str) -> tuple[int, str]:
    async with AsyncSessionFactory.public() as public:
        created = await _service(public, url, actor).create_family(owner, name)
    return created.tenant_id, created.owner.password


async def test_only_an_instance_administrator_gets_the_service(instance: str) -> None:
    """Covers: KAL-ADM-001"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Nowakowie", ANIA)
    member = await _sign_in(instance, ANIA, password)
    assert member.tenant is not None

    async with AsyncSessionFactory.public() as public:
        granted = await InstanceAdminService.for_actor(
            public,
            subject=admin,
            email=ADMIN,
            auth_backend="local",
            admin_emails=frozenset(),
            remover=RegistryAuthProvider(),
        )
        assert [f.tenant_id for f in await granted.families()][-1] == tenant_id
        with pytest.raises(NotFoundError):
            await InstanceAdminService.for_actor(
                public,
                subject=member.tenant.auth_subject,
                email=ANIA,
                auth_backend="local",
                admin_emails=frozenset({ANIA}),  # read only on a Supabase instance
                remover=RegistryAuthProvider(),
            )
        # Supabase: the operator's list decides; there are no local flags.
        supabase = await InstanceAdminService.for_actor(
            public,
            subject="00000000-0000-4000-8000-000000000009",
            email="Owner@Example.com",
            auth_backend="supabase",
            admin_emails=frozenset({"owner@example.com"}),
            remover=RegistryAuthProvider(),
        )
        assert supabase is not None
        with pytest.raises(NotFoundError):
            await InstanceAdminService.for_actor(
                public,
                subject=admin,
                email=ADMIN,
                auth_backend="supabase",
                admin_emails=frozenset({"owner@example.com"}),
                remover=RegistryAuthProvider(),
            )


async def test_a_family_is_created_with_a_one_time_password_for_its_owner(instance: str) -> None:
    """Covers: KAL-ADM-002"""
    admin = await _admin_subject(instance)

    tenant_id, password = await _create_family(instance, admin, " Kowalscy ", "Jan@Example.com")

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        family = await service.family(tenant_id)
        login = await service.login_by_email(JAN)
    assert family.name == "Kowalscy"
    assert family.owner_email == JAN
    assert family.members == 1
    assert family.status is TenantStatus.ACTIVE
    assert family.owner_signed_in is False
    assert login.must_change_password
    assert not login.is_admin

    signed_in = await _sign_in(instance, JAN, password)
    assert signed_in.tenant is not None
    assert signed_in.tenant.tenant_id == tenant_id
    async with AsyncSessionFactory.public() as public:
        assert (await _service(public, instance, admin).family(tenant_id)).owner_signed_in


async def test_a_family_needs_a_name_and_a_free_address(instance: str) -> None:
    """Covers: KAL-ADM-002"""
    admin = await _admin_subject(instance)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        with pytest.raises(ValidationError):
            await service.create_family(JAN, "   ")
        with pytest.raises(ValidationError):
            await service.create_family(JAN, "x" * 101)
        with pytest.raises(Exception, match="already exists"):
            await service.create_family(ADMIN, "Kowalscy")
        assert [f.name for f in await service.families()] == [None]


async def test_suspend_resume_and_delete_a_family(instance: str) -> None:
    """Covers: KAL-ADM-003"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)

    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).suspend(tenant_id)
    with pytest.raises(UnauthorizedError):
        await _sign_in(instance, JAN, password)

    async with AsyncSessionFactory.public() as public:
        await _service(public, instance, admin).resume(tenant_id)
    await _sign_in(instance, JAN, password)

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        with pytest.raises(ValidationError):
            await service.delete(tenant_id, typed="Kowalsk")
        with pytest.raises(ValidationError):
            await service.delete(tenant_id, typed=None)  # only kaleta-admin may skip it
        assert (await service.family(tenant_id)).status is TenantStatus.ACTIVE

        deleted = await service.delete(tenant_id, typed="Kowalscy")

        assert deleted.identities_removed == 1
        assert await public.get(Tenant, tenant_id) is None
        assert await LocalIdentityService(public).get_by_email(JAN) is None
        assert await LocalIdentityService(public).get_by_email(ADMIN) is not None


async def test_a_family_that_signed_itself_up_is_confirmed_by_its_owners_address(
    instance: str,
) -> None:
    """Covers: KAL-ADM-003"""
    admin = await _admin_subject(instance)
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_registration_mode(RegistrationMode.OPEN)
    result = await RegistryAuthProvider().sign_up(ANIA, PASSWORD)
    assert result.identity is not None
    signed_in = await _Flow(instance).complete(result.identity)
    assert signed_in.tenant is not None

    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        family = await service.family(signed_in.tenant.tenant_id)
        assert family.name is None
        assert family.label == ANIA
        await service.delete(family.tenant_id, typed=ANIA)


async def test_a_password_reset_signs_the_members_browsers_out(instance: str) -> None:
    """Covers: KAL-ADM-004"""
    admin = await _admin_subject(instance)
    tenant_id, password = await _create_family(instance, admin, "Kowalscy", JAN)
    signed_in = await _sign_in(instance, JAN, password)
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        row = await identities.get_by_email(JAN)
        assert row is not None
        await identities.set_password(row.id, PASSWORD)  # what the owner chose
        assert not (await identities.get(row.id)).must_change_password  # type: ignore[union-attr]

    async with AsyncSessionFactory.public() as public:
        reset = await _service(public, instance, admin).reset_password(row.id)

    assert reset.login.email == JAN
    assert reset.sessions_revoked
    assert reset.mfa_removed is None
    with pytest.raises(UnauthorizedError):
        await RegistryAuthProvider().sign_in(JAN, PASSWORD)
    assert isinstance(await RegistryAuthProvider().sign_in(JAN, reset.login.password), Identity)
    async with AsyncSessionFactory.public() as public:
        assert (await LocalIdentityService(public).get(row.id)).must_change_password  # type: ignore[union-attr]
        membership = await TenantService(public).get_member_by_subject(f"local:{row.id}")
    assert membership is not None and membership.tenant.id == tenant_id
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            assert await AuthService(session).sessions_valid_from(signed_in.user_id) is not None


async def test_the_last_administrator_stays_one(instance: str) -> None:
    """Covers: KAL-ADM-005"""
    admin = await _admin_subject(instance)
    await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        admin_row = await service.login_by_email(ADMIN)
        jan = await service.login_by_email(JAN)

        await service.set_admin(jan.identity_id, True)
        assert {r.email for r in await service.logins() if r.is_admin} == {ADMIN, JAN}

        await service.set_admin(admin_row.identity_id, False)
        assert [r.email for r in await service.logins() if r.is_admin] == [JAN]

        with pytest.raises(ValidationError, match="last administrator"):
            await service.set_admin(jan.identity_id, False)
        with pytest.raises(ValidationError, match="last administrator"):
            await service.set_disabled(jan.identity_id, True)
        assert [r.email for r in await service.logins() if r.is_admin] == [JAN]


async def test_every_action_leaves_an_audit_row_without_the_targets_address(
    instance: str,
) -> None:
    """Covers: KAL-ADM-006"""
    admin = await _admin_subject(instance)
    tenant_id, _password = await _create_family(instance, admin, "Kowalscy", JAN)
    async with AsyncSessionFactory.public() as public:
        service = _service(public, instance, admin)
        jan = await service.login_by_email(JAN)
        await service.suspend(tenant_id)
        await service.reset_password(jan.identity_id)
        await service.set_registration_mode(RegistrationMode.OPEN)
        await service.set_registration_mode(RegistrationMode.OPEN)  # no change, no row
        trail = await service.audit_trail()

    assert [(e.action, e.tenant_id, e.identity_id, e.detail) for e in trail] == [
        (AdminAction.REGISTRATION_CHANGED, None, None, "open"),
        (AdminAction.PASSWORD_RESET, None, jan.identity_id, None),
        (AdminAction.FAMILY_SUSPENDED, tenant_id, None, None),
        (AdminAction.FAMILY_CREATED, tenant_id, jan.identity_id, None),
        (AdminAction.LOGIN_CREATED, None, jan.identity_id, None),
    ]
    assert {e.actor for e in trail} == {admin}
    for entry in trail:
        assert JAN not in " ".join(str(v) for v in vars(entry).values())

    out = io.StringIO()
    cli = tenant_admin.TenantAdminCli(AsyncSessionFactory.public, RegistryAuthProvider(), out=out)
    assert await cli.resume(tenant_id) == 0
    async with AsyncSessionFactory.public() as public:
        newest = (
            (await public.execute(select(AdminAuditEntry).order_by(AdminAuditEntry.id.desc())))
            .scalars()
            .first()
        )
    assert newest is not None
    assert (newest.action, newest.actor, newest.tenant_id) == (
        AdminAction.FAMILY_RESUMED,
        None,
        tenant_id,
    )
