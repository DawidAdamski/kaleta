# SPDX-License-Identifier: AGPL-3.0-or-later
"""Upcoming planned rows merged into the ledger, end to end over a real DB.

Covers: KAL-PLN-023, KAL-PLN-024
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    PlannedTransactionService,
    TransactionService,
)

pytestmark = pytest.mark.asyncio

# The literals below are the ones written into the scenarios in docs/bdd.md.
TODAY = datetime.date(2026, 3, 3)
RENT_DUE = datetime.date(2026, 3, 5)
WINDOW_END = TODAY + datetime.timedelta(days=7)


async def _account(session: AsyncSession, name: str = "PKO Main") -> int:
    acc = await AccountService(session).create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _category(session: AsyncSession, name: str, cat_type: CategoryType) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _rent_plan(session: AsyncSession, account_id: int) -> int:
    plan = await PlannedTransactionService(session).create(
        PlannedTransactionCreate(
            name="Rent",
            amount=Decimal("2500.00"),
            type=TransactionType.EXPENSE,
            account_id=account_id,
            frequency=RecurrenceFrequency.MONTHLY,
            start_date=RENT_DUE,
        )
    )
    return plan.id


async def test_an_upcoming_occurrence_reaches_the_ledger_as_a_planned_row(
    session: AsyncSession,
) -> None:
    """Covers: KAL-PLN-023 — the control case: nothing posted, one promise shown."""
    account_id = await _account(session)
    plan_id = await _rent_plan(session, account_id)

    svc = PlannedTransactionService(session)
    rows = PlannedTransactionService.build_upcoming_rows(
        await svc.upcoming_for_ledger(TODAY, WINDOW_END),
        TODAY,
    )

    assert [row["id"] for row in rows] == [f"planned:{plan_id}:2026-03-05"]
    assert rows[0]["days_ahead"] == 2
    assert rows[0]["amount"] == "-2,500.00"


async def test_a_posted_occurrence_is_not_promised_a_second_time(session: AsyncSession) -> None:
    """Covers: KAL-PLN-023"""
    account_id = await _account(session)
    plan_id = await _rent_plan(session, account_id)

    svc = PlannedTransactionService(session)
    posted = await svc.post_occurrence(plan_id, RENT_DUE)

    upcoming = await svc.upcoming_for_ledger(TODAY, WINDOW_END)
    assert upcoming == []

    actuals = await TransactionService(session).list(search="Rent")
    assert [tx.id for tx in actuals] == [posted.id]

    merged = TransactionService.merge_upcoming_rows(
        TransactionService.build_table_rows(actuals, "none"),
        PlannedTransactionService.build_upcoming_rows(upcoming, TODAY),
        "none",
    )
    assert [row.get("is_planned", False) for row in merged] == [False]


async def test_the_month_net_counts_the_records_and_not_the_promise(
    session: AsyncSession,
) -> None:
    """Covers: KAL-PLN-024

    The expected net is the figure written into the scenario, not one this
    test recomputes from the rows it just built.
    """
    account_id = await _account(session)
    await _rent_plan(session, account_id)
    income_cat = await _category(session, "Wynagrodzenie", CategoryType.INCOME)
    expense_cat = await _category(session, "Zywnosc", CategoryType.EXPENSE)

    tx_svc = TransactionService(session)
    await tx_svc.create(
        TransactionCreate(
            account_id=account_id,
            category_id=income_cat,
            amount=Decimal("9240.00"),
            type=TransactionType.INCOME,
            date=datetime.date(2026, 3, 1),
            description="Salary",
        )
    )
    await tx_svc.create(
        TransactionCreate(
            account_id=account_id,
            category_id=expense_cat,
            amount=Decimal("128.74"),
            type=TransactionType.EXPENSE,
            date=datetime.date(2026, 3, 2),
            description="Lidl",
        )
    )

    upcoming = await PlannedTransactionService(session).upcoming_for_ledger(TODAY, WINDOW_END)
    merged = TransactionService.merge_upcoming_rows(
        TransactionService.build_table_rows(await tx_svc.list(), "month"),
        PlannedTransactionService.build_upcoming_rows(upcoming, TODAY),
        "month",
    )

    assert [row.get("is_planned", False) for row in merged] == [True, False, False]
    assert merged[0]["sep_label"] == "March 2026"
    assert merged[0]["sep_net"] == "+9,111.26"
