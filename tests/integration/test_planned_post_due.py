# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for posting due planned transactions.

Covers: KAL-PLN-016, KAL-PLN-017
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.services import AccountService, PlannedTransactionService

pytestmark = pytest.mark.asyncio


async def test_post_all_due_posts_weekly_window(session: AsyncSession) -> None:
    """Covers: KAL-PLN-016"""
    acc = await AccountService(session).create(
        AccountCreate(name="PKO Main", type=AccountType.CHECKING)
    )
    svc = PlannedTransactionService(session)
    pt = await svc.create(
        PlannedTransactionCreate(
            name="Groceries",
            amount=Decimal("300.00"),
            type=TransactionType.EXPENSE,
            account_id=acc.id,
            frequency=RecurrenceFrequency.WEEKLY,
            start_date=datetime.date(2025, 1, 1),
        )
    )
    posted = await svc.post_due(as_of=datetime.date(2025, 1, 15), lookback_days=30)
    assert len(posted) == 3
    assert all(tx.planned_transaction_id == pt.id for tx in posted)
    assert {tx.date for tx in posted} == {
        datetime.date(2025, 1, 1),
        datetime.date(2025, 1, 8),
        datetime.date(2025, 1, 15),
    }


async def test_repost_same_occurrence_is_idempotent(session: AsyncSession) -> None:
    """Covers: KAL-PLN-017"""
    acc = await AccountService(session).create(
        AccountCreate(name="PKO Main", type=AccountType.CHECKING)
    )
    svc = PlannedTransactionService(session)
    pt = await svc.create(
        PlannedTransactionCreate(
            name="Rent",
            amount=Decimal("2500.00"),
            type=TransactionType.EXPENSE,
            account_id=acc.id,
            frequency=RecurrenceFrequency.MONTHLY,
            start_date=datetime.date(2025, 1, 1),
        )
    )
    first = await svc.post_occurrence(pt.id, datetime.date(2025, 1, 1))
    second = await svc.post_occurrence(pt.id, datetime.date(2025, 1, 1))
    assert first.id == second.id
    count = await session.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.planned_transaction_id == pt.id,
            Transaction.date == datetime.date(2025, 1, 1),
        )
    )
    assert count == 1
