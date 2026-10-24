# SPDX-License-Identifier: AGPL-3.0-or-later
"""Loan-linked transactions stay out of every spending/income reader (KAL-DBT-005).

KAL-DBT-004 fixed ``ReportService`` and ``MoneyFlowService``; this covers the
broadened exclusion across the other income/expense readers. The fixture mirrors
``tests/unit/services/test_loan_ledger_link.py`` (``_account``/``_category``/``_tx``/
``_lend``) and adds an incoming loan (borrowing) so the income-side readers have a
loan-linked income transaction to exclude.

All literals here are taken from scenario KAL-DBT-005 (rule 11):
3000.00 salary, 120.00 groceries, a 400.00 outgoing loan and a 900.00 borrowing.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.personal_loan import LoanDirection
from kaleta.models.transaction import TransactionType, TransferDirection
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.personal_loan import PersonalLoanCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    CategoryService,
    PersonalLoanService,
    TransactionService,
)
from kaleta.services.budget_service import BudgetService
from kaleta.services.reserve_fund_service import ReserveFundService
from kaleta.services.salary_service import SalaryService
from kaleta.services.scenario_service import ScenarioService

# Everything is booked on this day; the readers are asked as of the next month,
# so September 2026 is a complete, past month for the income baselines.
BOOKED = datetime.date(2026, 9, 26)
AS_OF = datetime.date(2026, 10, 1)


async def _account(session: AsyncSession, name: str = "Konto") -> int:
    acc = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    return acc.id


async def _category(session: AsyncSession, name: str, cat_type: CategoryType) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _tx(
    session: AsyncSession,
    *,
    account_id: int,
    amount: str,
    tx_type: TransactionType = TransactionType.EXPENSE,
    category_id: int | None = None,
    description: str = "",
) -> int:
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=Decimal(amount),
            type=tx_type,
            transfer_direction=(
                TransferDirection.OUT if tx_type == TransactionType.TRANSFER else None
            ),
            date=BOOKED,
            description=description,
        )
    )
    return tx.id


async def _lend(
    session: AsyncSession,
    name: str,
    principal: str,
    *,
    transaction_id: int,
    direction: LoanDirection = LoanDirection.OUTGOING,
) -> int:
    svc = PersonalLoanService(session)
    cp = await svc.upsert_counterparty(name)
    loan = await svc.create_loan(
        PersonalLoanCreate(
            counterparty_id=cp.id,
            direction=direction,
            principal=Decimal(principal),
            opened_at=BOOKED,
            transaction_id=transaction_id,
        )
    )
    return loan.id


async def _setup(session: AsyncSession) -> tuple[int, int]:
    """Seed KAL-DBT-005: 3000 salary, 120 groceries, a 400 lend, a 900 borrow.

    Returns ``(account_id, groceries_category_id)``.
    """
    acc = await _account(session)
    food = await _category(session, "Jedzenie", CategoryType.EXPENSE)
    salary = await _category(session, "Pensja", CategoryType.INCOME)

    await _tx(
        session,
        account_id=acc,
        amount="3000.00",
        tx_type=TransactionType.INCOME,
        category_id=salary,
    )
    await _tx(session, account_id=acc, amount="120.00", category_id=food)

    # Lent out: a grocery-category expense that must not count as spending.
    lent = await _tx(session, account_id=acc, amount="400.00", category_id=food)
    await _lend(session, "Marek", "400.00", transaction_id=lent)

    # Borrowed: incoming cash that must not count as income.
    borrowed = await _tx(
        session, account_id=acc, amount="900.00", tx_type=TransactionType.INCOME, category_id=salary
    )
    await _lend(
        session, "Ania", "900.00", transaction_id=borrowed, direction=LoanDirection.INCOMING
    )
    return acc, food


class TestLoanLinkedExclusion:
    async def test_budget_actuals_exclude_the_outgoing_loan(self, session: AsyncSession) -> None:
        """Covers: KAL-DBT-005"""
        _, food = await _setup(session)

        grid = await BudgetService(session).actuals_by_category_month(2026)

        # Groceries in September: only the real 120.00, not the 400.00 lent.
        assert grid[(food, 9)] == Decimal("120.00")

    async def test_salary_income_baseline_excludes_the_borrowing(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-DBT-005"""
        await _setup(session)

        months, _ = await SalaryService(session).income_by_month(today=AS_OF)

        september = {(m.year, m.month): m.total for m in months}[(2026, 9)]
        assert september == Decimal("3000.00")

    async def test_reserve_burn_rate_excludes_the_outgoing_loan(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-DBT-005"""
        await _setup(session)

        burn = await ReserveFundService(session).trailing_monthly_expense(today=AS_OF)

        # 120.00 of spending over the fixed 3-month window; the 400.00 lent is out.
        assert burn == Decimal("40.00")

    async def test_scenario_trailing_income_excludes_the_borrowing(
        self, session: AsyncSession
    ) -> None:
        """Covers: KAL-DBT-005"""
        await _setup(session)

        income = await ScenarioService(session).trailing_monthly_income(today=AS_OF)

        # 3000.00 of income over the fixed 3-month window; the 900.00 borrowed is out.
        assert income == Decimal("1000.00")
