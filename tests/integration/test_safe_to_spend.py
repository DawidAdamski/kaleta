# SPDX-License-Identifier: AGPL-3.0-or-later
"""The phone hero's one figure, over a real database.

Covers: KAL-DSH-006 — income, spending and a plan still due all come from the
ledger here rather than from a hand-made summary, because what the hero has
to agree with is the ledger. Every number below is a literal from the
scenario; none of them is computed by calling the service under test.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.schemas.account import AccountCreate, AccountType
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionType
from kaleta.services import (
    AccountService,
    CategoryService,
    PlannedTransactionService,
    ReportService,
    TransactionService,
)

# June 2026 has 30 days; the scenario stands on its 10th.
TODAY = datetime.date(2026, 6, 10)


@pytest.mark.asyncio
async def test_safe_to_spend_is_income_less_committed_less_spent(session: AsyncSession) -> None:
    account = await AccountService(session).create(
        AccountCreate(
            name="Checking", type=AccountType.CHECKING, balance=Decimal("0.00"), currency="PLN"
        )
    )
    categories = CategoryService(session)
    salary = await categories.create(CategoryCreate(name="Salary", type=CategoryType.INCOME))
    food = await categories.create(CategoryCreate(name="Food", type=CategoryType.EXPENSE))

    transactions = TransactionService(session)
    await transactions.create(
        TransactionCreate(
            account_id=account.id,
            category_id=salary.id,
            amount=Decimal("6000.00"),
            type=TransactionType.INCOME,
            date=datetime.date(2026, 6, 1),
            description="Salary",
        )
    )
    await transactions.create(
        TransactionCreate(
            account_id=account.id,
            category_id=food.id,
            amount=Decimal("1500.00"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2026, 6, 4),
            description="Groceries",
        )
    )
    await PlannedTransactionService(session).create(
        PlannedTransactionCreate(
            name="Rent",
            amount=Decimal("2200.00"),
            type=TransactionType.EXPENSE,
            account_id=account.id,
            frequency=RecurrenceFrequency.ONCE,
            start_date=datetime.date(2026, 6, 28),
        )
    )

    result = await ReportService(session).safe_to_spend(today=TODAY)

    assert result.income == Decimal("6000.00")
    assert result.spent == Decimal("1500.00")
    assert result.committed == Decimal("2200.00")
    assert result.free == Decimal("2300.00")
    assert result.days_left == 21
    # The service rounds to the grosz itself; no formatter has to.
    assert result.per_day == Decimal("109.52")
