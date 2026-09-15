# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ReportService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.budget import BudgetCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate
from kaleta.services import (
    AccountService,
    BudgetService,
    CategoryService,
    PayeeService,
    PlannedTransactionService,
    TransactionService,
)
from kaleta.services.report_service import (
    BudgetVarianceRow,
    CategoryAmount,
    ReportService,
    SafeToSpend,
    SavingsRatePoint,
    SpendingByCategory,
    YoYComparison,
    YoYRow,
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
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("5000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=rent,
            amount=Decimal("1500"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )

        stmt = await svc.income_statement(2025, 6)

        assert stmt.total_income == Decimal("5000")
        assert stmt.total_expenses == Decimal("1900")
        assert stmt.net_income == Decimal("3100")
        assert {c.category for c in stmt.income_by_category} == {"Salary"}
        assert {c.category for c in stmt.expense_by_category} == {"Food", "Rent"}

    async def test_ignores_other_months(self, svc: ReportService, session: AsyncSession) -> None:
        acc = await _make_account(session)
        cat = await _make_category(session, "Food")
        await _make_tx(
            session,
            account_id=acc,
            category_id=cat,
            amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 5, 30),
        )
        stmt = await svc.income_statement(2025, 6)
        assert stmt.total_expenses == Decimal("0")

    async def test_ignores_internal_transfers(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        await _make_tx(
            session,
            account_id=acc,
            category_id=None,
            amount=Decimal("500"),
            tx_type=TransactionType.TRANSFER,
            date=datetime.date(2025, 6, 1),
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
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("3000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("1000"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        cfs = await svc.cash_flow_statement(2025, 6)
        assert cfs.total_inflows == Decimal("3000")
        assert cfs.total_outflows == Decimal("1000")
        assert cfs.net_cash_flow == Decimal("2000")


# ── budget_variance ────────────────────────────────────────────────────────────


class TestBudgetVarianceRowArithmetic:
    """The two signs a variance row carries, kept apart on purpose.

    Figures are the three over-budget rows drawn in artboard 1c.
    """

    def test_overspend_is_positive_when_past_plan(self) -> None:
        row = BudgetVarianceRow(
            category="Żywność", planned=Decimal("1400.00"), actual=Decimal("1612.30")
        )

        assert row.overspend == Decimal("212.30")
        assert row.variance == Decimal("-212.30")
        assert row.over_budget is True

    def test_spent_pct_counts_up_from_the_plan(self) -> None:
        row = BudgetVarianceRow(
            category="Rozrywka", planned=Decimal("300.00"), actual=Decimal("418.00")
        )

        # 139% of plan — not the -39% that variance_pct reports.
        assert round(row.spent_pct or Decimal("0")) == Decimal("139")
        assert round(row.variance_pct or Decimal("0")) == Decimal("-39")

    def test_a_row_just_past_plan(self) -> None:
        row = BudgetVarianceRow(
            category="Transport", planned=Decimal("350.00"), actual=Decimal("372.40")
        )

        assert round(row.spent_pct or Decimal("0")) == Decimal("106")
        assert row.overspend == Decimal("22.40")

    def test_an_unbudgeted_row_has_no_percentage(self) -> None:
        row = BudgetVarianceRow(category="Fun", planned=Decimal("0"), actual=Decimal("50"))

        assert row.spent_pct is None
        assert row.over_budget is False
        # Not "over" its plan and not severely over it either — one row, one answer.
        assert row.is_severely_over(Decimal("110")) is False


class TestBudgetVarianceSeverity:
    """Where a row falls against a threshold — artboard 1c's three rows."""

    def test_fifteen_percent_over_is_severe(self) -> None:
        row = BudgetVarianceRow(
            category="Żywność", planned=Decimal("1400.00"), actual=Decimal("1612.30")
        )

        assert row.is_severely_over(Decimal("110")) is True

    def test_thirty_nine_percent_over_is_severe(self) -> None:
        row = BudgetVarianceRow(
            category="Rozrywka", planned=Decimal("300.00"), actual=Decimal("418.00")
        )

        assert row.is_severely_over(Decimal("110")) is True

    def test_six_percent_over_is_not(self) -> None:
        row = BudgetVarianceRow(
            category="Transport", planned=Decimal("350.00"), actual=Decimal("372.40")
        )

        assert row.is_severely_over(Decimal("110")) is False

    def test_exactly_at_the_threshold_is_severe(self) -> None:
        row = BudgetVarianceRow(category="x", planned=Decimal("100"), actual=Decimal("110"))

        assert row.is_severely_over(Decimal("110")) is True

    def test_the_signed_variance_cannot_be_mistaken_for_it(self) -> None:
        # variance_pct is negative when over budget: comparing *it* against the
        # threshold classified every over-budget row as a warning.
        row = BudgetVarianceRow(category="x", planned=Decimal("1400.00"), actual=Decimal("1612.30"))

        assert (row.variance_pct or Decimal("0")) < Decimal("110")
        assert row.is_severely_over(Decimal("110")) is True


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
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("600"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 6, 5),
        )
        # Fun: spent 100 with no plan → unbudgeted
        await _make_tx(
            session,
            account_id=acc,
            category_id=fun,
            amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 6, 6),
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
            session,
            account_id=acc,
            category_id=cat,
            amount=Decimal("50"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 6, 1),
        )
        rep = await svc.budget_variance(2025, 6)
        assert rep.rows[0].variance_pct is None


# ── savings_rate ───────────────────────────────────────────────────────────────


class TestSavingsRate:
    async def test_rate_computed_per_month(self, svc: ReportService, session: AsyncSession) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food")

        today = datetime.date.today()
        # Same-month income 1000, expenses 400 → 60% rate.
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=today.replace(day=1),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE,
            date=today.replace(day=1),
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
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=rent,
            amount=Decimal("1500"),
            tx_type=TransactionType.EXPENSE,
            date=d,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("5000"),
            tx_type=TransactionType.INCOME,
            date=d,
        )
        rep = await svc.spending_by_category(datetime.date(2025, 6, 1), datetime.date(2025, 7, 1))
        assert [r.category for r in rep.rows] == ["Rent", "Food"]
        assert rep.total == Decimal("1700")

    async def test_split_lines_feed_category_totals(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """Covers: KAL-SPL-003"""
        acc = await _make_account(session)
        groceries = await _make_category(session, "Groceries")
        alcohol = await _make_category(session, "Alcohol")
        d = datetime.date(2025, 6, 15)
        await TransactionService(session).create(
            TransactionCreate(
                account_id=acc,
                amount=Decimal("214.50"),
                type=TransactionType.EXPENSE,
                date=d,
                description="Lidl",
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=groceries, amount=Decimal("180.00")),
                    TransactionSplitCreate(category_id=alcohol, amount=Decimal("34.50")),
                ],
            )
        )
        rep = await svc.spending_by_category(datetime.date(2025, 6, 1), datetime.date(2025, 7, 1))
        by_cat = {row.category: row.amount for row in rep.rows}
        assert by_cat["Groceries"] == Decimal("180.00")
        assert by_cat["Alcohol"] == Decimal("34.50")


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
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("50"),
            tx_type=TransactionType.EXPENSE,
            date=d,
            payee_id=biedronka,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("75"),
            tx_type=TransactionType.EXPENSE,
            date=d,
            payee_id=biedronka,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE,
            date=d,
            payee_id=lidl,
        )
        merchants = await svc.top_merchants(datetime.date(2025, 6, 1), datetime.date(2025, 7, 1))
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
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2024, 3, 5),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("150"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2025, 3, 5),
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
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("20000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(2024, 3, 1),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("2000"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2024, 6, 1),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=rent,
            amount=Decimal("8000"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2024, 6, 1),
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
                session,
                account_id=acc,
                category_id=cat,
                amount=Decimal(amt),
                tx_type=TransactionType.EXPENSE,
                date=today,
            )
        rows = await svc.largest_transactions(days=7, limit=3)
        assert [r.amount for r in rows] == [Decimal("500"), Decimal("300"), Decimal("50")]

    async def test_filters_by_type(self, svc: ReportService, session: AsyncSession) -> None:
        acc = await _make_account(session)
        inc = await _make_category(session, "Salary", CategoryType.INCOME)
        exp = await _make_category(session, "Food")
        today = datetime.date.today()
        await _make_tx(
            session,
            account_id=acc,
            category_id=inc,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=today,
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=exp,
            amount=Decimal("500"),
            tx_type=TransactionType.EXPENSE,
            date=today,
        )
        rows = await svc.largest_transactions(days=7, limit=10, tx_type=TransactionType.EXPENSE)
        assert len(rows) == 1
        assert rows[0].type == TransactionType.EXPENSE


class TestReportDisplayHelpers:
    def test_average_savings_rate_pct_empty(self) -> None:
        assert ReportService.average_savings_rate_pct([]) == Decimal("0")

    def test_average_savings_rate_pct_with_none_rates(self) -> None:
        points = [
            SavingsRatePoint(2026, 1, Decimal("0"), Decimal("100")),
            SavingsRatePoint(2026, 2, Decimal("1000"), Decimal("800")),
        ]
        # month 1: no income -> 0%; month 2: 20% -> avg 10%
        assert ReportService.average_savings_rate_pct(points) == Decimal("10")

    def test_spending_by_category_share_pct(self) -> None:
        rep = SpendingByCategory(
            start=datetime.date(2026, 1, 1),
            end=datetime.date(2026, 1, 31),
            rows=[
                CategoryAmount("Food", Decimal("75")),
                CategoryAmount("Transport", Decimal("25")),
            ],
        )
        assert rep.share_pct(Decimal("75")) == Decimal("75")
        assert rep.total == Decimal("100")

    def test_spending_by_category_share_pct_zero_total(self) -> None:
        rep = SpendingByCategory(
            start=datetime.date(2026, 1, 1),
            end=datetime.date(2026, 1, 31),
            rows=[],
        )
        assert rep.share_pct(Decimal("50")) == Decimal("5000")

    def test_yoy_comparison_totals(self) -> None:
        rep = YoYComparison(
            year=2026,
            basis="expense",
            rows=[
                YoYRow(1, Decimal("100"), Decimal("80")),
                YoYRow(2, Decimal("200"), Decimal("150")),
            ],
        )
        assert rep.total_this_year == Decimal("300")
        assert rep.total_last_year == Decimal("230")
        assert rep.total_delta == Decimal("70")


class TestKpiDeltas:
    async def test_balance_delta_vs_days_ago(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        today = datetime.date.today()
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("100"),
            tx_type=TransactionType.EXPENSE,
            date=today,
        )
        delta = await svc.balance_delta_vs_days_ago(30)
        assert delta.absolute == Decimal("-100")
        assert delta.reference_date == today - datetime.timedelta(days=30)

    async def test_month_net_delta(self, svc: ReportService, session: AsyncSession) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food")
        today = datetime.date.today()

        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1

        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(prev_year, prev_month, 10),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("2000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(today.year, today.month, 10),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("500"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(today.year, today.month, 11),
        )

        delta = await svc.month_net_delta()
        assert delta.absolute == Decimal("500")
        assert delta.reference_year == prev_year
        assert delta.reference_month == prev_month

    async def test_savings_rate_delta(self, svc: ReportService, session: AsyncSession) -> None:
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food")
        today = datetime.date.today()

        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1

        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(prev_year, prev_month, 5),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("400"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(prev_year, prev_month, 6),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("1000"),
            tx_type=TransactionType.INCOME,
            date=datetime.date(today.year, today.month, 5),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("200"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(today.year, today.month, 6),
        )

        delta = await svc.savings_rate_delta()
        assert delta.rate_points == Decimal("20.0")


class TestCurrentMonthPoint:
    """The month card reads this month as one point rather than re-deriving it."""

    async def test_carries_income_expenses_savings_and_rate(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        today = datetime.date.today()
        acc = await _make_account(session)
        salary = await _make_category(session, "Salary", CategoryType.INCOME)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        await _make_tx(
            session,
            account_id=acc,
            category_id=salary,
            amount=Decimal("5000"),
            tx_type=TransactionType.INCOME,
            date=today.replace(day=1),
        )
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("4000"),
            tx_type=TransactionType.EXPENSE,
            date=today.replace(day=1),
        )

        point = await svc.current_month_point()

        assert (point.year, point.month) == (today.year, today.month)
        assert point.income == Decimal("5000")
        assert point.expenses == Decimal("4000")
        assert point.savings == Decimal("1000")
        assert point.rate_pct == Decimal("20")

    async def test_no_income_yet_means_no_rate(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        today = datetime.date.today()
        acc = await _make_account(session)
        food = await _make_category(session, "Food", CategoryType.EXPENSE)
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("120"),
            tx_type=TransactionType.EXPENSE,
            date=today.replace(day=1),
        )

        point = await svc.current_month_point()

        assert point.income == Decimal("0.00")
        assert point.rate_pct is None


class TestSavingsRatePointTarget:
    """`meets_target` is what colours the month card's savings bar."""

    def test_at_the_target_counts_as_met(self) -> None:
        point = SavingsRatePoint(2026, 7, Decimal("1000"), Decimal("800"))

        assert point.rate_pct == Decimal("20")
        assert point.meets_target(Decimal("20")) is True

    def test_below_the_target_does_not(self) -> None:
        point = SavingsRatePoint(2026, 7, Decimal("1000"), Decimal("900"))

        assert point.meets_target(Decimal("20")) is False

    def test_a_month_with_no_income_has_not_met_it(self) -> None:
        point = SavingsRatePoint(2026, 7, Decimal("0"), Decimal("120"))

        assert point.rate_pct is None
        assert point.meets_target(Decimal("20")) is False


# ── safe_to_spend (artboard 1f) ───────────────────────────────────────────────


async def _make_planned(
    session: AsyncSession,
    *,
    account_id: int,
    amount: Decimal,
    date: datetime.date,
    tx_type: TransactionType = TransactionType.EXPENSE,
    name: str = "Rent",
) -> None:
    await PlannedTransactionService(session).create(
        PlannedTransactionCreate(
            name=name,
            amount=amount,
            type=tx_type,
            account_id=account_id,
            frequency=RecurrenceFrequency.ONCE,
            start_date=date,
        )
    )


async def _seed_subscription(
    session: AsyncSession,
    name: str,
    amount: Decimal,
    next_expected_at: datetime.date,
) -> None:
    """An active subscription billing every 30 days, anchored on *next_expected_at*."""
    session.add(
        Subscription(
            name=name,
            amount=amount,
            cadence_days=30,
            first_seen_at=next_expected_at,
            next_expected_at=next_expected_at,
            status=SubscriptionStatus.ACTIVE,
        )
    )
    await session.flush()


class TestSafeToSpend:
    """The phone hero's one question: what is left of the month?

    Every figure below is a literal from KAL-DSH-006, not a re-derivation.
    The scenario itself is claimed over a real database in
    ``tests/integration/test_safe_to_spend.py``; these are its edges.
    """

    async def test_a_plan_already_behind_us_is_not_still_due(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """Committed looks forward from today, not back over the whole month.

        A plan dated the 5th has either posted (and is in ``spent``) or been
        missed; either way promising the money again would count it twice.
        """
        acc = await _make_account(session)
        await _make_planned(
            session,
            account_id=acc,
            amount=Decimal("300.00"),
            date=datetime.date(2026, 6, 5),
        )

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("0.00")

    async def test_planned_income_is_not_committed(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """Only money leaving is promised. Income counts once it has landed."""
        acc = await _make_account(session)
        await _make_planned(
            session,
            account_id=acc,
            amount=Decimal("900.00"),
            date=datetime.date(2026, 6, 20),
            tx_type=TransactionType.INCOME,
            name="Refund",
        )

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("0.00")
        assert result.income == Decimal("0.00")

    async def test_two_plans_of_the_same_amount_on_one_day_are_two_payments(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """The subscription de-duplication must not swallow a real duplicate."""
        acc = await _make_account(session)
        for name in ("Rent A", "Rent B"):
            await _make_planned(
                session,
                account_id=acc,
                amount=Decimal("50.00"),
                date=datetime.date(2026, 6, 20),
                name=name,
            )

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("100.00")

    async def test_a_subscription_matching_a_plan_by_day_and_amount_is_dropped(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """A known limit, pinned so it cannot change unnoticed.

        The only thing a projected subscription charge and a planned
        occurrence share is a date and an amount — no transaction carries a
        subscription id — so an unrelated subscription billing 49.99 on the
        same day as a 49.99 plan is taken for the same payment and counted
        once. Overstating what is safe to spend is the error this figure
        exists to avoid, so if the two ever gain a real link, undo this.
        """
        acc = await _make_account(session)
        await _make_planned(
            session,
            account_id=acc,
            amount=Decimal("49.99"),
            date=datetime.date(2026, 6, 20),
            name="Gym",
        )
        await _seed_subscription(session, "Streaming", Decimal("49.99"), datetime.date(2026, 6, 20))

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("49.99")

    async def test_one_plan_stands_in_for_one_charge_not_for_every_match(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """The other half of the same lesson the two-plans test teaches.

        One 49.99 plan and two unrelated 49.99 subscriptions on the 20th is
        two payments, not one: the plan can account for one of the charges
        and no more. Matching by membership let one plan cancel every charge
        that shared its day and amount, which overstates what is free.
        """
        acc = await _make_account(session)
        await _make_planned(
            session,
            account_id=acc,
            amount=Decimal("49.99"),
            date=datetime.date(2026, 6, 20),
            name="Gym",
        )
        for name in ("Streaming", "Music"):
            await _seed_subscription(session, name, Decimal("49.99"), datetime.date(2026, 6, 20))

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("99.98")

    async def test_a_subscription_on_its_own_day_is_committed(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """The other half of the rule above: no collision, no drop."""
        acc = await _make_account(session)
        await _make_planned(
            session,
            account_id=acc,
            amount=Decimal("49.99"),
            date=datetime.date(2026, 6, 20),
            name="Gym",
        )
        await _seed_subscription(session, "Streaming", Decimal("49.99"), datetime.date(2026, 6, 21))

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.committed == Decimal("99.98")

    async def test_trailing_average_divides_by_the_window_not_by_busy_days(
        self, svc: ReportService, session: AsyncSession
    ) -> None:
        """900 zł over one day of a 30-day window is 30 zł a day, not 900."""
        acc = await _make_account(session)
        food = await _make_category(session, "Food")
        await _make_tx(
            session,
            account_id=acc,
            category_id=food,
            amount=Decimal("900.00"),
            tx_type=TransactionType.EXPENSE,
            date=datetime.date(2026, 6, 3),
        )

        result = await svc.safe_to_spend(today=datetime.date(2026, 6, 10))

        assert result.trailing_avg_per_day == Decimal("30.00")


#: A zero month on the 10th of a 30-day one — every test below states only
#: what it changes. ``replace`` keeps the builder typed, which a dict spread
#: could not.
BLANK_MONTH = SafeToSpend(
    today=datetime.date(2026, 6, 10),
    income=Decimal("0.00"),
    committed=Decimal("0.00"),
    spent=Decimal("0.00"),
    trailing_avg_per_day=Decimal("0.00"),
)


class TestSafeToSpendArithmetic:
    """The derived properties, without a database behind them."""

    def test_the_last_day_of_the_month_still_has_one_day_left(self) -> None:
        """Today counts — and a zero divisor would make ``per_day`` undefined."""
        result = replace(BLANK_MONTH, today=datetime.date(2026, 6, 30), income=Decimal("210.00"))

        assert result.days_left == 1
        assert result.per_day == Decimal("210.00")

    def test_overspending_is_reported_not_clamped(self) -> None:
        """A hero that cannot say "you are 300 over" is not worth reading."""
        result = replace(BLANK_MONTH, income=Decimal("1000.00"), spent=Decimal("1300.00"))

        assert result.free == Decimal("-300.00")
        assert result.spendable is False
