# SPDX-License-Identifier: AGPL-3.0-or-later
"""Household sharing end to end on the registry: invite, join, approve, remove.

Each test builds its household through the services — the owner's sign-up and
passphrase, the invitation link, the invitee's sign-in and passphrase, the
owner's approval — and asserts what each member can and cannot reach.

Covers: KAL-HHS-001, KAL-HHS-002, KAL-HHS-003, KAL-HHS-004, KAL-HHS-005, KAL-HHS-006,
KAL-HHS-007, KAL-HHS-008, KAL-HHS-009, KAL-HHS-010, KAL-HHS-011, KAL-HHS-012
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from kaleta.auth.providers import RegistryAuthProvider
from kaleta.crypto import key_ring
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.exceptions import (
    ConflictError,
    EncryptionError,
    NotFoundError,
    TenantLockedError,
    UnauthorizedError,
)
from kaleta.models.payee import Payee
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus, TenantRole
from kaleta.models.user import User
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.household_service import HouseholdInvitations, HouseholdService
from kaleta.services.key_service import KeyService
from kaleta.services.local_identity_service import LocalIdentityService
from tests.household_helpers import (
    OWNER,
    PARTNER,
    PARTNER_PASSPHRASE,
    PASSWORD,
    Member,
    accept,
    act,
    add_payees,
    approved_partner,
    household_database,
    invite,
    joined_partner,
    key_service_call,
    member_id_of,
    owner_with_data,
    payee_names,
    set_up_passphrase,
    sign_in,
    sign_in_identity,
    unlock,
)
from tests.tenancy_helpers import identity

#: The payees ``owner_with_data`` writes (the scenarios' literals).
PAYEES = ["Biedronka", "Orlen"]


@pytest.fixture
async def household_db() -> AsyncIterator[str]:
    async with household_database() as url:
        yield url


async def _member_row(email: str) -> TenantMember:
    async with AsyncSessionFactory.public() as public:
        row = (
            await public.execute(select(TenantMember).where(TenantMember.email == email))
        ).scalar_one()
        public.expunge(row)
        return row


async def _key_version(tenant_id: int) -> int:
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, tenant_id)
        assert tenant is not None
        return tenant.key_version


async def _remove(owner: Member, email: str, *, rekey: bool = True) -> None:
    member_id = await member_id_of(owner, email)
    owner_key = owner.unlocked_key()

    async def _go(service: HouseholdService) -> None:
        await service.remove(member_id, owner_key, rekey=rekey)

    await act(owner, _go)


async def test_an_invitation_link_is_good_once_and_for_72_hours(household_db: str) -> None:
    """Covers: KAL-HHS-001"""
    owner = await owner_with_data(household_db)

    async def _invite(service: HouseholdService):  # type: ignore[no-untyped-def]
        return await service.invite(PARTNER)

    before = datetime.now(UTC)
    first = await act(owner, _invite)
    assert first.email == PARTNER
    assert (
        before + timedelta(hours=72) <= first.expires_at <= datetime.now(UTC) + timedelta(hours=72)
    )
    assert first.link("https://kaleta.example.com/") == (
        f"https://kaleta.example.com/join?token={first.token}"
    )

    # Inviting the same address again: the first link stops working.
    second = await act(owner, _invite)
    async with AsyncSessionFactory.public() as public:
        links = HouseholdInvitations(public)
        with pytest.raises(NotFoundError):
            await links.preview(first.token)
        assert (await links.preview(second.token)).email == PARTNER

    # Used once, it is spent.
    await accept(second.token)
    with pytest.raises(NotFoundError):
        await accept(second.token, "another password here")

    # Older than 72 hours: refused.
    async with AsyncSessionFactory.public() as public:
        service = await HouseholdService.for_subject(public, owner.subject)
        service._clock = lambda: datetime.now(UTC) - timedelta(hours=73)
        stale = await service.invite("ewa@example.com")
        with pytest.raises(NotFoundError):
            await HouseholdInvitations(public).preview(stale.token)


async def test_the_invitee_waits_without_seeing_any_data(household_db: str) -> None:
    """Covers: KAL-HHS-002"""
    owner = await owner_with_data(household_db)
    partner = await joined_partner(household_db, owner)

    row = await _member_row(PARTNER)
    assert row.status is TenantMemberStatus.PENDING
    assert row.tenant_id == owner.tenant_id
    assert row.public_key is not None and row.dek_sealed is None

    async def _status(service: KeyService) -> str:
        return await service.status()

    assert await key_service_call(partner, _status) == "awaiting_key"
    assert partner.unlocked_key() is None
    with use_tenant(partner.context()):
        async with AsyncSessionFactory() as session:
            with pytest.raises(TenantLockedError):
                await session.execute(select(Payee.name))

    # Pending members cannot use the household's tools either.
    async def _members(service: HouseholdService) -> object:
        return await service.members()

    with pytest.raises(UnauthorizedError):
        await act(partner, _members)


async def test_approved_members_work_on_the_same_ledger(household_db: str) -> None:
    """Covers: KAL-HHS-003"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)

    partner_key = partner.unlocked_key()
    owner_key = owner.unlocked_key()
    assert partner_key is not None and owner_key is not None
    assert partner_key.dek == owner_key.dek
    assert await payee_names(partner, partner_key) == PAYEES

    await add_payees(partner, partner_key, "Lidl")
    assert await payee_names(owner, owner_key) == [*PAYEES, "Lidl"]

    async def _members(service: HouseholdService):  # type: ignore[no-untyped-def]
        return await service.members()

    listed = {m.email: m for m in await act(owner, _members)}
    assert listed[PARTNER].status is TenantMemberStatus.ACTIVE
    assert listed[PARTNER].role is TenantRole.MEMBER
    assert listed[OWNER].role is TenantRole.OWNER
    fp = listed[PARTNER].fingerprint
    assert fp is not None and re.fullmatch(r"([0-9a-f]{4} ){7}[0-9a-f]{4}", fp)


async def test_the_owner_declines_a_pending_member(household_db: str) -> None:
    """Covers: KAL-HHS-004"""
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)
    member_id = await member_id_of(owner, PARTNER)

    async def _decline(service: HouseholdService):  # type: ignore[no-untyped-def]
        await service.decline(member_id)
        return [m.email for m in await service.members()]

    assert await act(owner, _decline) == [OWNER]
    async with AsyncSessionFactory.public() as public:
        assert await LocalIdentityService(public).get_by_email(PARTNER) is None


async def test_removing_a_member_rekeys_the_household(household_db: str) -> None:
    """Covers: KAL-HHS-005"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    old_key = owner.unlocked_key()
    assert old_key is not None and old_key.version == 1
    assert partner.unlocked_key() is not None

    await _remove(owner, PARTNER)

    # Signed out everywhere, and the unlock forgotten.
    assert partner.unlocked_key() is None
    with use_tenant(owner.context()):
        async with AsyncSessionFactory() as session:
            user = await session.get(User, partner.user_id)
            assert user is not None and user.sessions_valid_from is not None

    assert await _key_version(owner.tenant_id) == 2
    new_key = owner.unlocked_key()
    assert new_key is not None and new_key.version == 2 and new_key.dek != old_key.dek
    assert await payee_names(owner, new_key) == PAYEES
    with pytest.raises(EncryptionError):
        await payee_names(owner, old_key)
    # Every encrypted value carries the new version in its header.
    with use_tenant(owner.context()):
        async with AsyncSessionFactory() as session:
            stale = await session.scalar(
                select(func.count()).where(func.get_byte(Payee.__table__.c.name, 1) != 2)
            )
            assert stale == 0

    row = await _member_row(PARTNER)
    assert row.status is TenantMemberStatus.REMOVED and row.dek_sealed is None
    with pytest.raises(UnauthorizedError):
        await sign_in(household_db, PARTNER)


async def test_removing_without_rekey_keeps_the_key(household_db: str) -> None:
    """Covers: KAL-HHS-006"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)

    await _remove(owner, PARTNER, rekey=False)

    assert partner.unlocked_key() is None
    assert await _key_version(owner.tenant_id) == 1
    with pytest.raises(UnauthorizedError):
        await sign_in(household_db, PARTNER)


async def test_ownership_is_handed_over_before_the_owner_leaves(household_db: str) -> None:
    """Covers: KAL-HHS-007"""
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    owner_key = owner.unlocked_key()

    async def _leave(service: HouseholdService) -> None:
        await service.leave(owner_key)

    with pytest.raises(ConflictError, match="Hand the household to another member"):
        await act(owner, _leave)

    member_id = await member_id_of(owner, PARTNER)

    async def _transfer(service: HouseholdService) -> None:
        await service.transfer_ownership(member_id)

    await act(owner, _transfer)
    async with AsyncSessionFactory.public() as public:
        roles = dict(
            (
                await public.execute(
                    select(TenantMember.email, TenantMember.role).where(
                        TenantMember.tenant_id == owner.tenant_id
                    )
                )
            ).all()
        )
    assert roles == {PARTNER: TenantRole.OWNER, OWNER: TenantRole.MEMBER}


async def test_a_member_leaves_the_household(household_db: str) -> None:
    """Covers: KAL-HHS-008"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    partner_key = partner.unlocked_key()

    async def _leave(service: HouseholdService) -> None:
        await service.leave(partner_key)

    await act(partner, _leave)

    assert await _key_version(owner.tenant_id) == 2
    with pytest.raises(UnauthorizedError):
        await sign_in(household_db, PARTNER)
    new_key = owner.unlocked_key()
    assert new_key is not None and await payee_names(owner, new_key) == PAYEES


async def test_a_household_has_at_most_ten_members(household_db: str) -> None:
    """Covers: KAL-HHS-009"""
    owner = await owner_with_data(household_db)
    for n in range(9):
        await invite(owner, f"member{n}@example.com")
    with pytest.raises(ConflictError, match="at most 10 members"):
        await invite(owner, "one-too-many@example.com")


async def test_a_member_who_lost_their_keys_starts_over(household_db: str) -> None:
    """Covers: KAL-HHS-010"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)

    async def _reset(service: HouseholdService) -> None:
        await service.reset_keys()

    await act(partner, _reset)
    assert partner.unlocked_key() is None
    row = await _member_row(PARTNER)
    assert row.status is TenantMemberStatus.PENDING and row.public_key is None

    fresh = "a brand new passphrase"
    assert await set_up_passphrase(partner, fresh) is None
    member_id = await member_id_of(owner, PARTNER)
    owner_key = owner.unlocked_key()

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, owner_key)

    await act(owner, _approve)
    key = await unlock(partner, fresh)
    assert await payee_names(partner, key) == PAYEES


async def test_a_hosted_invitee_joins_by_verified_email(household_db: str) -> None:
    """Covers: KAL-HHS-011"""
    owner = await owner_with_data(household_db)
    await invite(owner, PARTNER)

    # A local login typed with the invited address joins nothing.
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_registration_mode(RegistrationMode.OPEN)
    await RegistryAuthProvider().sign_up(PARTNER, PASSWORD)
    impostor = await sign_in(household_db, PARTNER)
    assert impostor.tenant_id != owner.tenant_id
    # (That login now owns a family of its own, under the invited address —
    # take it out of the way for the hosted half.)
    async with AsyncSessionFactory.public() as public:
        await public.execute(TenantMember.__table__.delete().where(TenantMember.email == PARTNER))
        await public.commit()

    hosted = identity(7, email=PARTNER)
    membership = await sign_in_identity(household_db, hosted)
    assert membership.tenant.id == owner.tenant_id
    assert membership.member.status is TenantMemberStatus.PENDING
    assert membership.member.role is TenantRole.MEMBER
    assert membership.member.user_id is not None


async def test_a_removed_member_invited_again_starts_over(household_db: str) -> None:
    """Covers: KAL-HHS-012"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    await _remove(owner, PARTNER)

    await invite(owner, PARTNER)
    again = await sign_in(household_db, PARTNER)
    assert again.user_id == partner.user_id
    row = await _member_row(PARTNER)
    assert row.status is TenantMemberStatus.PENDING
    assert row.public_key is None and row.dek_sealed is None

    async def _status(service: KeyService) -> str:
        return await service.status()

    assert await key_service_call(again, _status) == "setup_required"
    assert await set_up_passphrase(again, PARTNER_PASSPHRASE) is None
    member_id = await member_id_of(owner, PARTNER)
    owner_key = owner.unlocked_key()

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, owner_key)

    await act(owner, _approve)
    key = await unlock(again, PARTNER_PASSPHRASE)
    assert await payee_names(again, key) == PAYEES
    assert key_ring.get(again.browser) is not None
