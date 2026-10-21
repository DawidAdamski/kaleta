# SPDX-License-Identifier: AGPL-3.0-or-later
"""Merging duplicate transactions must carry a duplicate's links to the keeper.

A duplicate may be the row that carries a fund-item link
(``irregular_item_id``) or a planned-occurrence link
(``planned_transaction_id``) the keeper lacks. Deleting the duplicate must
not drop that link.

Covers: KAL-DUP-001, KAL-DUP-002
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.irregular_item import IrregularItem
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.reserve_fund import ReserveFund, ReserveFundKind
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.services import AccountService, DedupeService

DATE = datetime.date(2026, 4, 10)


async def _account(session: AsyncSession) -> int:
    created = await AccountService(session).create(
        AccountCreate(name="Checking", type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    return created.id


async def _fund(session: AsyncSession) -> int:
    fund = ReserveFund(
        name="Wydatki nieregularne",
        kind=ReserveFundKind.IRREGULAR,
        target_amount=Decimal("0.00"),
    )
    session.add(fund)
    await session.commit()
    await session.refresh(fund)
    return fund.id


async def _irregular_item(session: AsyncSession, fund_id: int, name: str) -> int:
    item = IrregularItem(fund_id=fund_id, name=name, yearly_amount=Decimal("1200.00"))
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item.id


async def _planned(session: AsyncSession, account_id: int) -> int:
    plan = PlannedTransaction(
        name="Ubezpieczenie",
        amount=Decimal("-50.00"),
        type=TransactionType.EXPENSE,
        account_id=account_id,
        frequency=RecurrenceFrequency.YEARLY,
        start_date=DATE,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan.id


async def _tx(
    session: AsyncSession,
    *,
    account_id: int,
    irregular_item_id: int | None = None,
    planned_transaction_id: int | None = None,
) -> Transaction:
    tx = Transaction(
        account_id=account_id,
        type=TransactionType.EXPENSE,
        amount=Decimal("-50.00"),
        date=DATE,
        description="UBEZPIECZENIE",
        irregular_item_id=irregular_item_id,
        planned_transaction_id=planned_transaction_id,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


class TestMergeKeepsLinks:
    """Covers: KAL-DUP-001"""

    async def test_keeper_inherits_fund_and_plan_links_from_duplicate(self, session: AsyncSession):
        acc = await _account(session)
        fund_id = await _fund(session)
        item_id = await _irregular_item(session, fund_id, "Ubezpieczenie OC")
        plan_id = await _planned(session, acc)
        # Keeper has no links; the duplicate carries both.
        keeper = await _tx(session, account_id=acc)
        dupe = await _tx(
            session,
            account_id=acc,
            irregular_item_id=item_id,
            planned_transaction_id=plan_id,
        )
        keeper_id, dupe_id = keeper.id, dupe.id

        deleted = await DedupeService(session).merge_transactions(
            keeper_id=keeper_id, other_ids=[dupe_id]
        )

        assert deleted == 1
        session.expire_all()
        remaining = (await session.execute(select(Transaction.id))).scalars().all()
        assert keeper_id in remaining
        assert dupe_id not in remaining
        refreshed = await session.get(Transaction, keeper_id)
        assert refreshed is not None
        assert refreshed.irregular_item_id == item_id
        assert refreshed.planned_transaction_id == plan_id


class TestMergeDoesNotOverwriteKeeperLink:
    """Covers: KAL-DUP-002"""

    async def test_keeper_keeps_its_own_fund_link(self, session: AsyncSession):
        acc = await _account(session)
        fund_id = await _fund(session)
        keeper_item_id = await _irregular_item(session, fund_id, "Keeper item")
        dupe_item_id = await _irregular_item(session, fund_id, "Dupe item")
        keeper = await _tx(session, account_id=acc, irregular_item_id=keeper_item_id)
        dupe = await _tx(session, account_id=acc, irregular_item_id=dupe_item_id)
        keeper_id, dupe_id = keeper.id, dupe.id

        deleted = await DedupeService(session).merge_transactions(
            keeper_id=keeper_id, other_ids=[dupe_id]
        )

        assert deleted == 1
        session.expire_all()
        refreshed = await session.get(Transaction, keeper_id)
        assert refreshed is not None
        assert refreshed.irregular_item_id == keeper_item_id
        remaining = (await session.execute(select(Transaction.id))).scalars().all()
        assert dupe_id not in remaining
