"""Unit tests for ReportService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import (
    AccountService,
    BudgetService,
    CategoryService,
    PayeeService,
    ReportService,
    TransactionService,
)

# ── Fixtures & helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> ReportService:
    return ReportService(session)


async def _make_account(session: AsyncSession, name: str = "Checking") -> int:
    acc = await AccountService(session).create(
        AccountCreate(name=name, type=AccountType.CHECKING, balance=Decimal("0.00"))
    )
    return acc.id


async def _make_category(
    session: AsyncSession,
    name: str,
    cat_type: CategoryType = CategoryType.EXPENSE,
) -> int:
    cat = await CategoryService(session).create(CategoryCreate(name=name, type=cat_type))
    return cat.id


async def _make_payee(session: AsyncSession, name: str) -> int:
    p = await PayeeService(session).create(PayeeCreate(name=name))
    return p.id


async def _make_tx(
    session: AsyncSession,
    *,
    account_id: int,
    category_id: int | None,
    amount: Decimal,
    tx_type: TransactionType,
    date: datetime.date,
    payee_id: int | None = None,
    description: str = "",
    is_internal_transfer: bool = False,
) -> None:
    await TransactionService(session).create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            amount=amount,
            type=tx_type,
            date=date,
            description=description,
            payee_id=payee_id,
            is_internal_transfer=is_internal_transfer,
        )
    )


# ── income_statement ───────────────────────────────────────────────────────────


class TestIncomeStatement:
    async def test_groups_by_category_and_computes_totals(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        rent = await _make_category(session, "Rent", CategoryType.EXPENSE)

        d = datetime.date(2025, 6, 15)
        await _make_tx(
            session, account_id=acc, category_id=salary, amount=Decimal("5000"),
            tx_type=TransactionType.INCOME, date=d,
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE, date=d,
        )
        await _make_tx(
            session, account_id=acc, category_id=rent, amount=Decimal("1500"),
            tx_type=TransactionType.EXPENSE, date=d,
        )

        stmt = await svc.income_statement(2025, 6)

        assert stmt.total_income == Decimal("5000")
        assert stmt.total_expenses == Decimal("1900")
        assert stmt.net_income == Decimal("3100")
        assert {c.category for c in stmt.income_by_category} == {"Salary"}
        assert {c.category for c in stmt.expense_by_category} == {"Food", "Rent"}

    async def test_ignores_other_months(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        cat = await _make_category(session, "Food")
        await _make_tx(
            session, account_id=acc, category_id=cat, amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2025, 5, 30),
        )
        stmt = await svc.income_statement(2025, 6)
        assert stmt.total_expenses == Decimal("0")

    async def test_ignores_internal_transfers(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        await _make_tx(
            session, account_id=acc, category_id=None, amount=Decimal("500"),
            tx_type=TransactionType.TRANSFER, date=datetime.date(2025, 6, 1),
            is_internal_transfer=True,
        )
        stmt = await svc.income_statement(2025, 6)
        assert stmt.total_income == Decimal("0")
        assert stmt.total_expenses == Decimal("0")


# ── cash_flow_statement ────────────────────────────────────────────────────────


class TestCashFlowStatement:
    async def test_mirrors_income_statement_totals(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        d = datetime.date(2025, 6, 10)
        await _make_tx(
            session, account_id=acc, category_id=salary, amount=Decimal("3000"),
            tx_type=TransactionType.INCOME, date=d,
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("1000"),
            tx_type=TransactionType.EXPENSE, date=d,
        )
        cfs = await svc.cash_flow_statement(2025, 6)
        assert cfs.total_inflows == Decimal("3000")
        assert cfs.total_outflows == Decimal("1000")
        assert cfs.net_cash_flow == Decimal("2000")


# ── budget_variance ────────────────────────────────────────────────────────────


class TestBudgetVariance:
    async def test_includes_planned_and_unplanned_categories(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        fun = await _make_category(session, "Fun")
        await BudgetService(session).create(
            BudgetCreate(category_id=food, amount=Decimal("500"), month=6, year=2025)
        )
        # Food: spent 600 / 500 → over budget
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("600"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2025, 6, 5),
        )
        # Fun: spent 100 with no plan → unbudgeted
        await _make_tx(
            session, account_id=acc, category_id=fun, amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2025, 6, 6),
        )

        rep = await svc.budget_variance(2025, 6)
        by_cat = {r.category: r for r in rep.rows}
        assert by_cat["Food"].planned == Decimal("500")
        assert by_cat["Food"].actual == Decimal("600")
        assert by_cat["Food"].over_budget is True
        assert by_cat["Food"].variance == Decimal("-100")
        assert by_cat["Fun"].planned == Decimal("0")
        assert by_cat["Fun"].actual == Decimal("100")
        assert rep.total_planned == Decimal("500")
        assert rep.total_actual == Decimal("700")
        assert len(rep.over_budget_rows) == 1

    async def test_zero_planned_gives_none_variance_pct(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        cat = await _make_category(session, "Fun")
        await _make_tx(
            session, account_id=acc, category_id=cat, amount=Decimal("50"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2025, 6, 1),
        )
        rep = await svc.budget_variance(2025, 6)
        assert rep.rows[0].variance_pct is None


# ── savings_rate ───────────────────────────────────────────────────────────────


class TestSavingsRate:
    async def test_rate_computed_per_month(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food")

        today = datetime.date.today()
        # Same-month income 1000, expenses 400 → 60% rate.
        await _make_tx(
            session, account_id=acc, category_id=salary, amount=Decimal("1000"),
            tx_type=TransactionType.INCOME, date=today.replace(day=1),
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE, date=today.replace(day=1),
        )
        points = await svc.savings_rate(months=1)
        assert len(points) == 1
        p = points[0]
        assert p.income == Decimal("1000")
        assert p.expenses == Decimal("400")
        assert p.savings == Decimal("600")
        assert p.rate_pct == Decimal("60")

    async def test_no_income_gives_none_rate(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        points = await svc.savings_rate(months=1)
        assert points[0].rate_pct is None


# ── spending_by_category ───────────────────────────────────────────────────────


class TestSpendingByCategory:
    async def test_ranks_descending_and_ignores_income(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        rent = await _make_category(session, "Rent")
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        d = datetime.date(2025, 6, 10)
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE, date=d,
        )
        await _make_tx(
            session, account_id=acc, category_id=rent, amount=Decimal("1500"),
            tx_type=TransactionType.EXPENSE, date=d,
        )
        await _make_tx(
            session, account_id=acc, category_id=salary, amount=Decimal("5000"),
            tx_type=TransactionType.INCOME, date=d,
        )
        rep = await svc.spending_by_category(
            datetime.date(2025, 6, 1), datetime.date(2025, 7, 1)
        )
        assert [r.category for r in rep.rows] == ["Rent", "Food"]
        assert rep.total == Decimal("1700")


# ── top_merchants ──────────────────────────────────────────────────────────────


class TestTopMerchants:
    async def test_groups_by_payee_and_sorts_by_spend(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        biedronka = await _make_payee(session, "Biedronka")
        lidl = await _make_payee(session, "Lidl")
        d = datetime.date(2025, 6, 1)
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("50"),
            tx_type=TransactionType.EXPENSE, date=d, payee_id=biedronka,
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("75"),
            tx_type=TransactionType.EXPENSE, date=d, payee_id=biedronka,
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE, date=d, payee_id=lidl,
        )
        merchants = await svc.top_merchants(
            datetime.date(2025, 6, 1), datetime.date(2025, 7, 1)
        )
        assert [m.name for m in merchants] == ["Lidl", "Biedronka"]
        assert merchants[0].amount == Decimal("200")
        assert merchants[0].count == 1
        assert merchants[1].amount == Decimal("125")
        assert merchants[1].count == 2


# ── yoy_comparison ─────────────────────────────────────────────────────────────


class TestYoYComparison:
    async def test_twelve_rows_this_year_vs_last_year(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2024, 3, 5),
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("150"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2025, 3, 5),
        )
        rep = await svc.yoy_comparison(2025)
        assert rep.year == 2025
        assert rep.basis == "expense"
        assert len(rep.rows) == 12
        march = rep.rows[2]
        assert march.this_year == Decimal("150")
        assert march.last_year == Decimal("100")
        assert march.delta == Decimal("50")
        assert march.delta_pct == Decimal("50")


# ── ytd_summary ────────────────────────────────────────────────────────────────


class TestYTDSummary:
    async def test_past_year_totals_and_top_categories(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food")
        rent = await _make_category(session, "Rent")
        await _make_tx(
            session, account_id=acc, category_id=salary, amount=Decimal("20000"),
            tx_type=TransactionType.INCOME, date=datetime.date(2024, 3, 1),
        )
        await _make_tx(
            session, account_id=acc, category_id=food, amount=Decimal("2000"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2024, 6, 1),
        )
        await _make_tx(
            session, account_id=acc, category_id=rent, amount=Decimal("8000"),
            tx_type=TransactionType.EXPENSE, date=datetime.date(2024, 6, 1),
        )
        rep = await svc.ytd_summary(2024)
        assert rep.income == Decimal("20000")
        assert rep.expenses == Decimal("10000")
        assert rep.net == Decimal("10000")
        assert rep.savings_rate_pct == Decimal("50")
        assert rep.top_expense_categories[0].category == "Rent"


# ── largest_transactions ───────────────────────────────────────────────────────


class TestLargestTransactions:
    async def test_returns_top_n_in_descending_amount(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        cat = await _make_category(session, "Food")
        today = datetime.date.today()
        for amt in [10, 500, 300, 50]:
            await _make_tx(
                session, account_id=acc, category_id=cat, amount=Decimal(amt),
                tx_type=TransactionType.EXPENSE, date=today,
            )
        rows = await svc.largest_transactions(days=7, limit=3)
        assert [r.amount for r in rows] == [Decimal("500"), Decimal("300"), Decimal("50")]

    async def test_filters_by_type(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        inc = await _make_category(session, "Salary", CategoryType.INCOME)
        exp = await _make_category(session, "Food")
        today = datetime.date.today()
        await _make_tx(
            session, account_id=acc, category_id=inc, amount=Decimal("1000"),
            tx_type=TransactionType.INCOME, date=today,
        )
        await _make_tx(
            session, account_id=acc, category_id=exp, amount=Decimal("500"),
            tx_type=TransactionType.EXPENSE, date=today,
        )
        rows = await svc.largest_transactions(
            days=7, limit=10, tx_type=TransactionType.EXPENSE
        )
        assert len(rows) == 1
        assert rows[0].type == TransactionType.EXPENSE
