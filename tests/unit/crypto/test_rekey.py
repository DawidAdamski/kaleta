# SPDX-License-Identifier: AGPL-3.0-or-later
"""``HouseholdRekey``: every value moves to the new key, or none does.

On a registry database of the test's own (a household needs two members and a
real tenant schema); the scenario-level checks are in
``tests/integration/test_household_isolation.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, or_, select

from kaleta.crypto import DataKey, key_ring
from kaleta.db import AsyncSessionFactory
from kaleta.db.base import Base
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import EncryptedJSON, EncryptedText, exact_index, use_data_key
from kaleta.exceptions import ConflictError, EncryptionError
from kaleta.models.account import Account
from kaleta.models.payee import Payee
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus, TenantStatus
from kaleta.services import data_encryption_service
from kaleta.services.household_service import HouseholdService
from kaleta.services.key_service import KeyService
from kaleta.services.setup_service import release_interrupted_rekeys
from tests.household_helpers import (
    OWNER_PASSPHRASE,
    PARTNER,
    Member,
    act,
    add_payees,
    approved_partner,
    household_database,
    key_service_call,
    member_id_of,
    owner_with_data,
    payee_names,
)

ACCOUNT_NUMBER = "61 1090 1014 0000 0712 1981 2874"


@pytest.fixture
async def household_db() -> AsyncIterator[str]:
    async with household_database() as url:
        yield url


async def _with_account(owner: Member) -> None:
    key = owner.unlocked_key()
    assert key is not None
    with use_tenant(owner.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            session.add(Account(name="Konto wspólne", external_account_number=ACCOUNT_NUMBER))
            await session.commit()


async def _remove_partner(owner: Member) -> None:
    member_id = await member_id_of(owner, PARTNER)
    key = owner.unlocked_key()

    async def _go(service: HouseholdService) -> None:
        await service.remove(member_id, key)

    await act(owner, _go)


async def _tenant(tenant_id: int) -> Tenant:
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, tenant_id)
        assert tenant is not None
        public.expunge(tenant)
        return tenant


async def _values_not_under(owner: Member, version: int) -> int:
    """Encrypted values anywhere in the schema whose header names another key version."""
    stale = 0
    with use_tenant(owner.context()):
        async with AsyncSessionFactory() as session:
            for table in Base.metadata.sorted_tables:
                columns = [
                    c for c in table.columns if isinstance(c.type, (EncryptedText, EncryptedJSON))
                ]
                if not columns:
                    continue
                stale += int(
                    await session.scalar(
                        select(func.count())
                        .select_from(table)
                        .where(
                            or_(
                                *(
                                    (func.get_byte(c, 0) == 1) & (func.get_byte(c, 1) != version)
                                    for c in columns
                                )
                            )
                        )
                    )
                    or 0
                )
    return stale


async def test_every_encrypted_column_and_blind_index_moves_to_the_new_key(
    household_db: str,
) -> None:
    owner = await owner_with_data(household_db)
    await _with_account(owner)
    await approved_partner(household_db, owner)
    old = owner.unlocked_key()
    assert old is not None
    assert await _values_not_under(owner, 1) == 0

    await _remove_partner(owner)

    new = owner.unlocked_key()
    assert new is not None and new.version == 2
    assert await _values_not_under(owner, 2) == 0
    with use_tenant(owner.context(new)), use_data_key(new):
        async with AsyncSessionFactory() as session:
            account = (await session.execute(select(Account))).scalar_one()
            assert account.name == "Konto wspólne"
            assert account.external_account_number == ACCOUNT_NUMBER
            # The index is the new key's: an equality lookup under it finds the row.
            found = await session.scalar(
                select(Payee.name).where(Payee.name_bidx == exact_index("Orlen"))
            )
            assert found == "Orlen"
    with use_data_key(old):
        old_index = exact_index("Orlen")
    with use_data_key(new):
        assert exact_index("Orlen") != old_index
    # The old key reads nothing any more.
    with pytest.raises(EncryptionError):
        await payee_names(owner, old)


async def test_the_old_key_cannot_read_rows_written_after(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    old = owner.unlocked_key()
    assert old is not None
    await _remove_partner(owner)
    new = owner.unlocked_key()
    assert new is not None
    await add_payees(owner, new, "Lidl")

    forged = DataKey(old.dek, version=new.version)
    with pytest.raises(EncryptionError, match="Could not decrypt"):
        await payee_names(owner, forged)


async def test_an_interrupted_rekey_changes_nothing_and_runs_again(
    household_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    old = owner.unlocked_key()
    assert old is not None
    real = data_encryption_service.DataEncryptionService.rewrite_all
    seen: dict[str, object] = {}

    async def _crash(self, **kwargs):  # type: ignore[no-untyped-def]
        # Mid-pass: the household is frozen and marked; then the process "dies".
        seen["frozen"] = key_ring.is_frozen(owner.tenant_id)
        seen["owner_unlock"] = key_ring.get(owner.browser)
        seen["status"] = (await _tenant(owner.tenant_id)).status
        await real(self, **kwargs)
        msg = "simulated crash"
        raise RuntimeError(msg)

    monkeypatch.setattr(data_encryption_service.DataEncryptionService, "rewrite_all", _crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        await _remove_partner(owner)
    assert seen == {"frozen": True, "owner_unlock": None, "status": TenantStatus.REKEYING}

    # Rolled back: old key, old rows, partner still in, the household thawed.
    tenant = await _tenant(owner.tenant_id)
    assert tenant.key_version == 1 and tenant.status is TenantStatus.ACTIVE
    assert not key_ring.is_frozen(owner.tenant_id)
    assert owner.unlocked_key() == old
    assert await payee_names(owner, old) == ["Biedronka", "Orlen"]
    async with AsyncSessionFactory.public() as public:
        status = await public.scalar(
            select(TenantMember.status).where(TenantMember.email == PARTNER)
        )
    assert status is TenantMemberStatus.ACTIVE

    monkeypatch.setattr(data_encryption_service.DataEncryptionService, "rewrite_all", real)
    await _remove_partner(owner)
    assert (await _tenant(owner.tenant_id)).key_version == 2
    assert await _values_not_under(owner, 2) == 0


async def test_a_write_that_lands_after_the_pass_is_swept(
    household_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row written under the old key once the pass has read the table."""
    owner = await owner_with_data(household_db)
    await approved_partner(household_db, owner)
    old = owner.unlocked_key()
    assert old is not None
    real = data_encryption_service.DataEncryptionService.rewrite_all

    async def _then_a_late_write(self, **kwargs):  # type: ignore[no-untyped-def]
        counts = await real(self, **kwargs)
        if kwargs.get("only_key_version") is None:
            # Another session, bound before the freeze, commits under the old key.
            await add_payees(owner, old, "Żabka")
        return counts

    monkeypatch.setattr(
        data_encryption_service.DataEncryptionService, "rewrite_all", _then_a_late_write
    )
    await _remove_partner(owner)

    new = owner.unlocked_key()
    assert new is not None and new.version == 2
    assert await _values_not_under(owner, 2) == 0
    assert await payee_names(owner, new) == ["Biedronka", "Orlen", "Żabka"]


async def test_a_frozen_household_refuses_new_unlocks(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    key_ring.freeze(owner.tenant_id)
    try:
        assert owner.unlocked_key() is None

        async def _unlock(service: KeyService) -> object:
            return await service.unlock(owner.browser, OWNER_PASSPHRASE)

        with pytest.raises(ConflictError, match="being re-keyed"):
            await key_service_call(owner, _unlock)
    finally:
        key_ring.thaw(owner.tenant_id)
    assert owner.unlocked_key() is not None


async def test_a_household_left_rekeying_by_a_crash_is_released(household_db: str) -> None:
    owner = await owner_with_data(household_db)
    async with AsyncSessionFactory.public() as public:
        tenant = await public.get(Tenant, owner.tenant_id)
        assert tenant is not None
        tenant.status = TenantStatus.REKEYING
        await public.commit()

    assert release_interrupted_rekeys(household_db) == 1
    assert (await _tenant(owner.tenant_id)).status is TenantStatus.ACTIVE
    assert release_interrupted_rekeys(household_db) == 0
