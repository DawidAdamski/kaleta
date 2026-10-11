# SPDX-License-Identifier: AGPL-3.0-or-later
"""A household on a registry database of the test's own (``hosted-household-sharing``).

An owner with a ``local`` login, a data passphrase and a little encrypted data;
members invited, joined and approved through the services, never by writing
registry rows by hand — the tests are about the flow those rows come from.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import select

from kaleta.auth.providers import RegistryAuthProvider, set_auth_provider
from kaleta.crypto import DataKey, KdfParams, key_ring
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.db.types import install_data_key_resolver, use_data_key
from kaleta.models.payee import Payee
from kaleta.schemas.identity import Identity
from kaleta.services.household_service import HouseholdInvitations, HouseholdService
from kaleta.services.key_service import KeyService, TenantKeyStore
from kaleta.services.tenant_service import TenantMembership, TenantService
from tests.tenancy_helpers import MetadataProvisioner, multi_tenant_database

OWNER = "jan@example.com"
PARTNER = "ania@example.com"
PASSWORD = "correct horse battery"
OWNER_PASSPHRASE = "our household passphrase"
PARTNER_PASSPHRASE = "ania's own long passphrase"
FAST = KdfParams(time_cost=1, memory_kib=8 * 1024, parallelism=1)


@dataclass
class Member:
    email: str
    subject: str
    tenant_id: int
    schema: str
    user_id: int
    #: What the key ring files this member's browser under.
    browser: str

    def context(self, key: DataKey | None = None) -> TenantContext:
        return TenantContext(
            tenant_id=self.tenant_id, schema=self.schema, member_user_id=self.user_id, key_ring=key
        )

    def unlocked_key(self) -> DataKey | None:
        entry = key_ring.get(self.browser)
        return entry.data_key if entry is not None else None


@asynccontextmanager
async def household_database() -> AsyncIterator[str]:
    """A fresh registry with local logins and encryption on — each test module's fixture."""
    set_auth_provider(RegistryAuthProvider())
    install_data_key_resolver(None)
    key_ring.clear()
    try:
        async with multi_tenant_database(encryption="passphrase", auth_backend="local") as url:
            yield url
    finally:
        key_ring.clear()
        set_auth_provider(None)


async def sign_in_identity(url: str, identity: Identity) -> TenantMembership:
    async with AsyncSessionFactory.public() as public:
        service = TenantService(public, provisioner=MetadataProvisioner(url))
        return await service.membership_for_sign_in(identity)


async def sign_in(url: str, email: str, password: str = PASSWORD) -> Member:
    identity = await RegistryAuthProvider().sign_in(email, password)
    assert isinstance(identity, Identity)
    membership = await sign_in_identity(url, identity)
    assert membership.member.user_id is not None
    return Member(
        email=email,
        subject=identity.subject,
        tenant_id=membership.tenant.id,
        schema=membership.tenant.schema_name,
        user_id=membership.member.user_id,
        browser=f"browser-of-{email}",
    )


async def key_service_call(member: Member, fn):  # type: ignore[no-untyped-def]
    """Run ``fn(KeyService)`` for ``member`` — what ``with_key_service`` does for a page."""
    with use_tenant(member.context()):
        async with AsyncSessionFactory.public() as public, AsyncSessionFactory() as data:
            store = TenantKeyStore(public, member.tenant_id, member.user_id)
            return await fn(KeyService(store, data, params=FAST))


async def set_up_passphrase(member: Member, passphrase: str) -> DataKey | None:
    async def _setup(service: KeyService) -> DataKey | None:
        return (await service.setup(member.browser, passphrase)).data_key

    return await key_service_call(member, _setup)


async def unlock(member: Member, passphrase: str) -> DataKey:
    async def _unlock(service: KeyService) -> DataKey:
        return (await service.unlock(member.browser, passphrase)).data_key

    return await key_service_call(member, _unlock)


async def owner_with_data(url: str) -> Member:
    """The first sign-up (the instance's administrator too), unlocked, with two payees."""
    result = await RegistryAuthProvider().sign_up(OWNER, PASSWORD)
    assert result.identity is not None
    owner = await sign_in(url, OWNER)
    key = await set_up_passphrase(owner, OWNER_PASSPHRASE)
    assert key is not None
    await add_payees(owner, key, "Biedronka", "Orlen")
    return owner


async def add_payees(member: Member, key: DataKey, *names: str) -> None:
    with use_tenant(member.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            session.add_all(Payee(name=name) for name in names)
            await session.commit()


async def payee_names(member: Member, key: DataKey) -> list[str]:
    with use_tenant(member.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(Payee.name).order_by(Payee.id))
            return list(result.scalars().all())


async def act(member: Member, fn):  # type: ignore[no-untyped-def]
    """Run ``fn(HouseholdService)`` as ``member``."""
    async with AsyncSessionFactory.public() as public:
        service = await HouseholdService.for_subject(public, member.subject)
        return await fn(service)


async def invite(owner: Member, email: str) -> str:
    async def _invite(service: HouseholdService) -> str:
        return (await service.invite(email)).token

    return await act(owner, _invite)


async def accept(token: str, password: str = PASSWORD) -> str:
    async with AsyncSessionFactory.public() as public:
        return await HouseholdInvitations(public).accept_with_password(token, password)


async def member_id_of(owner: Member, email: str) -> int:
    async def _members(service: HouseholdService) -> int:
        return next(m.member_id for m in await service.members() if m.email == email)

    return await act(owner, _members)


async def joined_partner(url: str, owner: Member, email: str = PARTNER) -> Member:
    """Invited, signed up through the link, signed in, passphrase set — not yet approved."""
    await accept(await invite(owner, email))
    partner = await sign_in(url, email)
    assert await set_up_passphrase(partner, PARTNER_PASSPHRASE) is None
    return partner


async def approved_partner(url: str, owner: Member, email: str = PARTNER) -> Member:
    partner = await joined_partner(url, owner, email)
    member_id = await member_id_of(owner, email)
    owner_key = owner.unlocked_key()

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, owner_key)

    await act(owner, _approve)
    await unlock(partner, PARTNER_PASSPHRASE)
    return partner
