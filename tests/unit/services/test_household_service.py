# SPDX-License-Identifier: AGPL-3.0-or-later
"""``HouseholdService`` rules: who may do what, and the invariants it keeps.

The flows themselves are in ``tests/integration/test_household_isolation.py``;
here are the refusals and edges around them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select

from kaleta.config import settings
from kaleta.crypto import (
    DataKey,
    KeyMaterial,
    fingerprint,
    generate_dek,
    key_ring,
    open_private_key,
    open_sealed,
)
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import use_data_key
from kaleta.exceptions import (
    ConflictError,
    NotFoundError,
    TenantLockedError,
    UnauthorizedError,
    ValidationError,
)
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus, TenantRole, TenantStatus
from kaleta.services.api_token_service import ApiTokenService
from kaleta.services.household_service import (
    HouseholdInvitations,
    HouseholdService,
    next_key_version,
)
from kaleta.services.local_identity_service import LocalIdentityService
from tests.household_helpers import (
    OWNER,
    PARTNER,
    PARTNER_PASSPHRASE,
    accept,
    act,
    approved_partner,
    household_database,
    invite,
    joined_partner,
    member_id_of,
    owner_with_data,
    set_up_passphrase,
    sign_in,
    sign_in_identity,
)
from tests.tenancy_helpers import identity


@pytest.fixture
async def household_db() -> AsyncIterator[str]:
    async with household_database() as url:
        yield url


async def _row(email: str) -> TenantMember:
    async with AsyncSessionFactory.public() as public:
        row = (
            await public.execute(select(TenantMember).where(TenantMember.email == email))
        ).scalar_one()
        public.expunge(row)
        return row


async def test_approve_seals_the_households_key_to_the_members_keypair(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)
    owner_key = owner.unlocked_key()
    assert owner_key is not None
    member_id = await member_id_of(owner, PARTNER)

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, owner_key)

    await act(owner, _approve)
    row = await _row(PARTNER)
    assert row.dek_sealed is not None and row.joined_at is not None
    material = KeyMaterial(
        public_key=row.public_key or b"",
        private_key_wrapped=row.private_key_wrapped or b"",
        private_key_salt=row.private_key_salt or b"",
        kdf_params=row.kdf_params or "",
        dek_sealed=row.dek_sealed,
    )
    private_key = open_private_key(material, PARTNER_PASSPHRASE)
    assert open_sealed(row.dek_sealed, private_key) == owner_key.dek

    # Twice is refused: they are no longer pending.
    with pytest.raises(ConflictError):
        await act(owner, _approve)


async def test_approving_needs_the_owner_unlocked(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)
    member_id = await member_id_of(owner, PARTNER)

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, None)

    with pytest.raises(TenantLockedError):
        await act(owner, _approve)


async def test_a_member_before_their_passphrase_cannot_be_approved(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await accept(await invite(owner, PARTNER))
    await sign_in(household_db, PARTNER)
    member_id = await member_id_of(owner, PARTNER)
    owner_key = owner.unlocked_key()

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, owner_key)

    with pytest.raises(ConflictError, match="not set up their data passphrase"):
        await act(owner, _approve)


async def test_only_the_owner_runs_the_household(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    owner_id = await member_id_of(owner, OWNER)

    async def _invite(service: HouseholdService) -> None:
        await service.invite("ewa@example.com")

    async def _remove(service: HouseholdService) -> None:
        await service.remove(owner_id, partner.unlocked_key())

    async def _transfer(service: HouseholdService) -> None:
        await service.transfer_ownership(owner_id)

    for action in (_invite, _remove, _transfer):
        with pytest.raises(UnauthorizedError, match="Only the household's owner"):
            await act(partner, action)


async def test_the_household_always_has_exactly_one_owner(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)
    owner_id = await member_id_of(owner, OWNER)
    pending_id = await member_id_of(owner, PARTNER)
    key = owner.unlocked_key()

    async def _remove_self(service: HouseholdService) -> None:
        await service.remove(owner_id, key)

    async def _transfer_to_pending(service: HouseholdService) -> None:
        await service.transfer_ownership(pending_id)

    async def _reset(service: HouseholdService) -> None:
        await service.reset_keys()

    for action in (_remove_self, _transfer_to_pending, _reset):
        with pytest.raises(ConflictError):
            await act(owner, action)
    async with AsyncSessionFactory.public() as public:
        owners = await public.scalar(
            select(func.count(TenantMember.id)).where(
                TenantMember.tenant_id == owner.tenant_id, TenantMember.role == TenantRole.OWNER
            )
        )
    assert owners == 1


async def test_the_member_limit_counts_members_and_open_invitations(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)

    async with AsyncSessionFactory.public() as public:
        service = await HouseholdService.for_subject(public, owner.subject, max_members=3)
        await service.invite("ewa@example.com")
        with pytest.raises(ConflictError, match="at most 3 members"):
            await service.invite("ola@example.com")
        # A cancelled invitation frees its place; re-inviting the same address replaces it.
        await service.cancel_invitation("ewa@example.com")
        await service.invite("ola@example.com")
        await service.invite("ola@example.com")
        assert [i.email for i in await service.invitations()] == ["ola@example.com"]


async def test_an_invitation_names_one_address(household_db: str) -> None:
    owner = await owner_with_data(household_db)

    async def _bad(service: HouseholdService) -> None:
        await service.invite("not an address")

    async def _own(service: HouseholdService) -> None:
        await service.invite(OWNER)

    with pytest.raises(ValidationError):
        await act(owner, _bad)
    with pytest.raises(ConflictError, match="already a member"):
        await act(owner, _own)
    async with AsyncSessionFactory.public() as public:
        with pytest.raises(NotFoundError):
            await HouseholdInvitations(public).preview("no-such-token")


async def test_a_pending_member_never_creates_the_households_key(household_db: str) -> None:
    """An owner who never set a passphrase: the invitee's set-up makes a keypair only."""
    from kaleta.auth.providers import RegistryAuthProvider

    await RegistryAuthProvider().sign_up(OWNER, "correct horse battery")
    owner = await sign_in(household_db, OWNER)
    token = await invite(owner, PARTNER)
    await accept(token)
    partner = await sign_in(household_db, PARTNER)

    assert await set_up_passphrase(partner, PARTNER_PASSPHRASE) is None
    row = await _row(PARTNER)
    assert row.public_key is not None and row.dek_sealed is None


async def test_with_encryption_off_a_pending_member_waits_outside(
    household_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await owner_with_data(household_db)
    await accept(await invite(owner, PARTNER))
    monkeypatch.setattr(settings, "encryption", "off")

    with pytest.raises(UnauthorizedError, match="waiting for the owner's approval"):
        await sign_in(household_db, PARTNER)

    member_id = await member_id_of(owner, PARTNER)

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, None)

    await act(owner, _approve)
    assert (await _row(PARTNER)).status is TenantMemberStatus.ACTIVE
    await sign_in(household_db, PARTNER)


def test_the_key_version_wraps_within_one_byte() -> None:
    assert next_key_version(1) == 2
    assert next_key_version(254) == 255
    assert next_key_version(255) == 1
    assert DataKey(generate_dek(), version=next_key_version(255)).version == 1


# ── After review: the edges around decline, removal and approval ────────────


async def _remove_partner(owner, *, rekey: bool) -> None:  # type: ignore[no-untyped-def]
    member_id = await member_id_of(owner, PARTNER)
    key = owner.unlocked_key()

    async def _go(service: HouseholdService) -> None:
        await service.remove(member_id, key, rekey=rekey)

    await act(owner, _go)


async def test_declining_a_returning_member_keeps_their_login_and_row(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    await _remove_partner(owner, rekey=True)
    await invite(owner, PARTNER)
    await sign_in(household_db, PARTNER)
    member_id = await member_id_of(owner, PARTNER)

    async def _decline(service: HouseholdService) -> None:
        await service.decline(member_id)

    await act(owner, _decline)
    row = await _row(PARTNER)
    assert row.status is TenantMemberStatus.REMOVED and row.user_id is not None
    async with AsyncSessionFactory.public() as public:
        assert await LocalIdentityService(public).get_by_email(PARTNER) is not None


@pytest.mark.parametrize("rekey", [True, False])
async def test_a_removed_members_api_tokens_stop_working(household_db: str, rekey: bool) -> None:
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    key = partner.unlocked_key()
    with use_tenant(partner.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            _token, raw = await ApiTokenService(session).create_token(
                user_id=partner.user_id, label="skrypt"
            )
            assert await ApiTokenService(session).authenticate_bearer(raw) == partner.user_id

    await _remove_partner(owner, rekey=rekey)

    new_key = owner.unlocked_key()
    with use_tenant(owner.context(new_key)), use_data_key(new_key):
        async with AsyncSessionFactory() as session:
            assert await ApiTokenService(session).authenticate_bearer(raw) is None


async def test_approval_needs_the_current_key_and_the_shown_keypair(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await joined_partner(household_db, owner)
    member_id = await member_id_of(owner, PARTNER)
    key = owner.unlocked_key()
    assert key is not None

    async def _approve(service: HouseholdService, k: DataKey, fp: str | None) -> None:
        await service.approve(member_id, k, expected_fingerprint=fp)

    stale = DataKey(key.dek, version=key.version + 1)
    with pytest.raises(ConflictError, match="not the household's current one"):
        await act(owner, lambda s: _approve(s, stale, None))
    with pytest.raises(ConflictError, match="key changed"):
        await act(owner, lambda s: _approve(s, key, "0000 0000 0000 0000 0000 0000 0000 0000"))
    key_ring.freeze(owner.tenant_id)
    try:
        with pytest.raises(ConflictError, match="being re-keyed"):
            await act(owner, lambda s: _approve(s, key, None))
    finally:
        key_ring.thaw(owner.tenant_id)
    shown = fingerprint((await _row(PARTNER)).public_key or b"")
    await act(owner, lambda s: _approve(s, key, shown))
    assert (await _row(PARTNER)).status is TenantMemberStatus.ACTIVE


async def test_a_second_rekey_of_one_household_is_refused(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, owner.tenant_id)
        assert tenant is not None
        tenant.status = TenantStatus.REKEYING
        await public.commit()

    with pytest.raises(ConflictError, match="being re-keyed already"):
        await _remove_partner(owner, rekey=True)
    # The refusal froze nothing, and the running re-key's mark stays.
    assert not key_ring.is_frozen(owner.tenant_id)
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, owner.tenant_id)
        assert tenant is not None and tenant.status is TenantStatus.REKEYING
    assert (await _row(PARTNER)).status is TenantMemberStatus.ACTIVE


async def test_an_invitation_for_an_address_with_a_login_asks_to_sign_in(
    household_db: str,
) -> None:
    owner = await owner_with_data(household_db)
    token = await invite(owner, PARTNER)
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).create(PARTNER, "some older password")
    with pytest.raises(ConflictError, match="Sign in with it"):
        await accept(token)
    async with AsyncSessionFactory.public() as public:
        # The link is still good: nothing was spent.
        assert (await HouseholdInvitations(public).preview(token)).email == PARTNER


async def test_an_unverified_hosted_address_joins_nothing(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await invite(owner, PARTNER)
    unverified = identity(8, email=PARTNER, verified=False)
    with pytest.raises(UnauthorizedError):
        await sign_in_identity(household_db, unverified)
    async with AsyncSessionFactory.public() as public:
        assert (
            await public.scalar(select(TenantMember.id).where(TenantMember.email == PARTNER))
        ) is None


async def test_re_inviting_at_the_limit_replaces_the_link(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    async with AsyncSessionFactory.public() as public:
        service = await HouseholdService.for_subject(public, owner.subject, max_members=2)
        first = await service.invite(PARTNER)
        second = await service.invite(PARTNER)
        assert first.token != second.token
        assert [i.email for i in await service.invitations()] == [PARTNER]
