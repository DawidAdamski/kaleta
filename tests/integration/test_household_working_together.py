# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two members working on one ledger: who changed what, who added what, and stale saves.

``hosted-household-sharing`` §4. Each test builds the household through the
services (``tests.household_helpers``) and then works in the family's schema as
one member or the other, the way each one's browser would.

Covers: KAL-HHS-015, KAL-HHS-016, KAL-HHS-017
"""

from __future__ import annotations

import datetime
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.db.types import use_data_key
from kaleta.exceptions import StaleWriteError
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.transaction import TransactionCreate, TransactionType, TransactionUpdate
from kaleta.services import (
    AccountService,
    AuditService,
    CategoryService,
    MemberNameService,
    TransactionService,
)
from tests.household_helpers import (
    Member,
    add_payees,
    approved_partner,
    household_database,
    owner_with_data,
)

#: One unit of work on the family's schema.
Work = Callable[[AsyncSession], Awaitable[Any]]


@pytest.fixture
async def household_db() -> AsyncIterator[str]:
    async with household_database() as url:
        yield url


async def _as[T](member: Member, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run ``fn`` on the family's schema as ``member``, with their unlocked key."""
    key = member.unlocked_key()
    assert key is not None
    with use_tenant(member.context(key)), use_data_key(key):
        async with AsyncSessionFactory() as session:
            return await fn(session)


async def _ledger(owner: Member) -> tuple[int, int]:
    """An account and an expense category, set up by the owner."""

    async def _make(session: AsyncSession) -> tuple[int, int]:
        account = await AccountService(session).create(AccountCreate(name="Wspólne konto"))
        category = await CategoryService(session).create(
            CategoryCreate(name="Zakupy", type=CategoryType.EXPENSE)
        )
        return account.id, category.id

    return await _as(owner, _make)


async def _add_expense(member: Member, account_id: int, category_id: int, text: str) -> int:
    async def _add(session: AsyncSession) -> int:
        tx = await TransactionService(session).create(
            TransactionCreate(
                account_id=account_id,
                category_id=category_id,
                amount=Decimal("42.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2026, 10, 1),
                description=text,
            )
        )
        return tx.id

    return await _as(member, _add)


async def test_the_history_says_which_member_made_each_change(household_db: str) -> None:
    """Covers: KAL-HHS-015"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    partner_key = partner.unlocked_key()
    assert partner_key is not None
    await add_payees(partner, partner_key, "Lidl")

    async def _history(session: AsyncSession) -> tuple[list[Any], dict[int, str]]:
        entries = await AuditService(session).list_for_display()
        return entries, await MemberNameService(session).names()

    entries, names = await _as(owner, _history)
    added = [e for e in entries if e.table_name == "payees" and e.operation == "INSERT"]
    # Newest first: Lidl (the partner's), then the owner's two.
    assert [names.get(e.user_id or 0) for e in added] == ["ania", "jan", "jan"]
    assert MemberNameService.is_household(names)


async def test_the_ledger_filters_by_who_added_a_row(household_db: str) -> None:
    """Covers: KAL-HHS-016"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    account_id, category_id = await _ledger(owner)
    await _add_expense(owner, account_id, category_id, "Biedronka")
    await _add_expense(partner, account_id, category_id, "Lidl")

    async def _added_by_partner(session: AsyncSession) -> tuple[list[str], int, dict[int, str]]:
        svc = TransactionService(session)
        rows = await svc.list(user_ids=[partner.user_id])
        total = await svc.count(user_ids=[partner.user_id])
        return [tx.description for tx in rows], total, await MemberNameService(session).names()

    descriptions, total, names = await _as(owner, _added_by_partner)
    assert descriptions == ["Lidl"]
    assert total == 1
    assert names[partner.user_id] == "ania"


async def test_a_save_over_someone_elses_change_is_refused(household_db: str) -> None:
    """Covers: KAL-HHS-017"""
    owner = await owner_with_data(household_db)
    partner = await approved_partner(household_db, owner)
    account_id, category_id = await _ledger(owner)
    tx_id = await _add_expense(owner, account_id, category_id, "Biedronka")

    async def _loaded(session: AsyncSession) -> datetime.datetime:
        tx = await TransactionService(session).get(tx_id)
        assert tx is not None
        return tx.updated_at

    # Both open the edit dialog on the same version of the row.
    owner_saw = await _as(owner, _loaded)
    partner_saw = await _as(partner, _loaded)
    assert owner_saw == partner_saw

    def _edit(text: str, seen: datetime.datetime | None) -> Work:
        async def _save(session: AsyncSession) -> Any:
            return await TransactionService(session).update(
                tx_id, TransactionUpdate(description=text, expected_updated_at=seen)
            )

        return _save

    await _as(partner, _edit("Biedronka — zakupy na tydzień", partner_saw))

    with pytest.raises(StaleWriteError) as refused:
        await _as(owner, _edit("Biedronka (jan)", owner_saw))
    assert refused.value.changed_by == "ania"

    async def _description(session: AsyncSession) -> str:
        tx = await TransactionService(session).get(tx_id)
        assert tx is not None
        return tx.description

    assert await _as(owner, _description) == "Biedronka — zakupy na tydzień"

    # Reloaded, the owner's save goes through; without a version, last write wins.
    await _as(owner, _edit("Biedronka (jan)", await _as(owner, _loaded)))
    await _as(partner, _edit("Biedronka", None))
    assert await _as(owner, _description) == "Biedronka"
