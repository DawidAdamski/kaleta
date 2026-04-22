"""Canned financial reports.

This service is the single source of truth for the "golden standard" reports
surfaced by the Reports library and by the Dashboard widgets. Each method
returns a typed dataclass so views and CSV export can share a shape.

Reports layer architecture:
- Low-level helpers (_month_bounds, _tx_in_range, etc.) sit at the top.
- Each public report method composes those helpers into a single query
  and returns a dataclass. No chart building here — that's view layer.
- Kept existing methods (`total_balance`, `current_month_summary`,
  `cashflow_last_n_months`, `recent_transactions`) because Dashboard + tests
  already consume them.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account
from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType

# ── Shared dataclasses ────────────────────────────────────────────────────────


@dataclass
class MonthCashflow:
    year: int
    month: int
    income: Decimal
    expenses: Decimal

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def net(self) -> Decimal:
        return self.income - self.expenses


@dataclass
class CategoryAmount:
    """Pair of (category name, amount) used across several reports."""

    category: str
    amount: Decimal


@dataclass
class IncomeStatement:
    """Personal P&L for a single month: income - expenses by category."""

    year: int
    month: int
    income_by_category: list[CategoryAmount]
    expense_by_category: list[CategoryAmount]

    @property
    def total_income(self) -> Decimal:
        return sum((c.amount for c in self.income_by_category), Decimal("0"))

    @property
    def total_expenses(self) -> Decimal:
        return sum((c.amount for c in self.expense_by_category), Decimal("0"))

    @property
    def net_income(self) -> Decimal:
        return self.total_income - self.total_expenses


@dataclass
class CashFlowStatement:
    """Operating cash in vs out, categorised, for a single month.

    For a personal-finance app there's no investing/financing split yet — all
    flows are treated as operating. That scaffolding can be added later if
    investment accounts are introduced.
    """

    year: int
    month: int
    inflows: list[CategoryAmount]
    outflows: list[CategoryAmount]

    @property
    def total_inflows(self) -> Decimal:
        return sum((c.amount for c in self.inflows), Decimal("0"))

    @property
    def total_outflows(self) -> Decimal:
        return sum((c.amount for c in self.outflows), Decimal("0"))

    @property
    def net_cash_flow(self) -> Decimal:
        return self.total_inflows - self.total_outflows


@dataclass
class BudgetVarianceRow:
    category: str
    planned: Decimal
    actual: Decimal

    @property
    def variance(self) -> Decimal:
        """Positive = under budget (good). Negative = over budget."""
        return self.planned - self.actual

    @property
    def variance_pct(self) -> Decimal | None:
        if self.planned == 0:
            return None
        return (self.variance / self.planned) * Decimal("100")

    @property
    def over_budget(self) -> bool:
        return self.actual > self.planned and self.planned > 0


@dataclass
class BudgetVarianceReport:
    year: int
    month: int
    rows: list[BudgetVarianceRow]

    @property
    def total_planned(self) -> Decimal:
        return sum((r.planned for r in self.rows), Decimal("0"))

    @property
    def total_actual(self) -> Decimal:
        return sum((r.actual for r in self.rows), Decimal("0"))

    @property
    def over_budget_rows(self) -> list[BudgetVarianceRow]:
        return [r for r in self.rows if r.over_budget]


@dataclass
class SavingsRatePoint:
    year: int
    month: int
    income: Decimal
    expenses: Decimal

    @property
    def savings(self) -> Decimal:
        return self.income - self.expenses

    @property
    def rate_pct(self) -> Decimal | None:
        """(income - expenses) / income, in %. None when no income."""
        if self.income <= 0:
            return None
        return (self.savings / self.income) * Decimal("100")

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass
class MerchantSpend:
    name: str
    amount: Decimal
    count: int


@dataclass
class YoYRow:
    month: int
    this_year: Decimal
    last_year: Decimal

    @property
    def delta(self) -> Decimal:
        return self.this_year - self.last_year

    @property
    def delta_pct(self) -> Decimal | None:
        if self.last_year == 0:
            return None
        return (self.delta / self.last_year) * Decimal("100")


@dataclass
class YoYComparison:
    year: int
    rows: list[YoYRow]  # one per month, 1..12
    basis: str  # "expense" or "income"


@dataclass
class YTDSummary:
    year: int
    income: Decimal
    expenses: Decimal
    top_expense_categories: list[CategoryAmount]

    @property
    def net(self) -> Decimal:
        return self.income - self.expenses

    @property
    def savings_rate_pct(self) -> Decimal | None:
        if self.income <= 0:
            return None
        return (self.net / self.income) * Decimal("100")


@dataclass
class LargeTransaction:
    date: datetime.date
    account: str
    category: str
    description: str
    amount: Decimal
    type: TransactionType


@dataclass
class SpendingByCategory:
    """Flat list of expense categories ranked by amount for a date range."""

    start: datetime.date
    end: datetime.date
    rows: list[CategoryAmount] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((r.amount for r in self.rows), Decimal("0"))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    """Return [start, end) for the given calendar month."""
    start = datetime.date(year, month, 1)
    end = (
        datetime.date(year + 1, 1, 1)
        if month == 12
        else datetime.date(year, month + 1, 1)
    )
    return start, end


# ── Service ───────────────────────────────────────────────────────────────────


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Legacy helpers (used by Dashboard) ───────────────────────────────────

    async def total_balance(self) -> Decimal:
        result = await self.session.execute(select(func.sum(Account.balance)))
        val = result.scalar()
        return Decimal(str(val)) if val else Decimal("0.00")

    async def current_month_summary(self) -> tuple[Decimal, Decimal]:
        today = datetime.date.today()
        start, end = _month_bounds(today.year, today.month)
        result = await self.session.execute(
            select(Transaction.type, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by(Transaction.type)
        )
        income = Decimal("0.00")
        expenses = Decimal("0.00")
        for row in result:
            if row.type == TransactionType.INCOME:
                income = Decimal(str(row.total))
            elif row.type == TransactionType.EXPENSE:
                expenses = Decimal(str(row.total))
        return income, expenses

    async def cashflow_last_n_months(self, n: int = 6) -> list[MonthCashflow]:
        today = datetime.date.today()
        months: list[tuple[int, int]] = []
        for i in range(n - 1, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            months.append((y, m))

        start_date = datetime.date(months[0][0], months[0][1], 1)

        result = await self.session.execute(
            select(
                func.strftime("%Y", Transaction.date).label("year"),
                func.strftime("%m", Transaction.date).label("month"),
                Transaction.type,
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.date >= start_date,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by("year", "month", Transaction.type)
            .order_by("year", "month")
        )

        data: dict[tuple[int, int], dict[str, Decimal]] = {
            (y, m): {"income": Decimal("0"), "expenses": Decimal("0")} for y, m in months
        }
        for row in result:
            key = (int(row.year), int(row.month))
            if key not in data:
                continue
            if row.type == TransactionType.INCOME:
                data[key]["income"] = Decimal(str(row.total))
            elif row.type == TransactionType.EXPENSE:
                data[key]["expenses"] = Decimal(str(row.total))

        return [
            MonthCashflow(
                year=y, month=m, income=data[(y, m)]["income"], expenses=data[(y, m)]["expenses"]
            )
            for y, m in months
        ]

    async def recent_transactions(self, limit: int = 10) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .options(selectinload(Transaction.account), selectinload(Transaction.category))
            .where(Transaction.is_internal_transfer == False)  # noqa: E712
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── Canonical finance reports ────────────────────────────────────────────

    async def income_statement(self, year: int, month: int) -> IncomeStatement:
        """Personal P&L for one month, broken out by category."""
        start, end = _month_bounds(year, month)
        rows = await self._sum_by_category(start, end)

        income_rows = [r for r in rows if r.type == TransactionType.INCOME]
        expense_rows = [r for r in rows if r.type == TransactionType.EXPENSE]

        return IncomeStatement(
            year=year,
            month=month,
            income_by_category=[
                CategoryAmount(category=r.name or "—", amount=Decimal(str(r.total)))
                for r in income_rows
            ],
            expense_by_category=[
                CategoryAmount(category=r.name or "—", amount=Decimal(str(r.total)))
                for r in expense_rows
            ],
        )

    async def cash_flow_statement(self, year: int, month: int) -> CashFlowStatement:
        """Operating cash in/out for the month.

        Same underlying query as income statement but framed as cash-flow
        buckets. Separated so the view can present a standard Cash Flow layout
        (inflows ↑ / outflows ↓) with its own narrative.
        """
        stmt = await self.income_statement(year, month)
        return CashFlowStatement(
            year=year,
            month=month,
            inflows=stmt.income_by_category,
            outflows=stmt.expense_by_category,
        )

    async def budget_variance(self, year: int, month: int) -> BudgetVarianceReport:
        """Plan vs actual per expense category for one month.

        Rows include every category that either had a budget OR had actual
        spending — so the view can surface under-budget AND unbudgeted blow-ups.
        """
        start, end = _month_bounds(year, month)

        budget_res = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(Budget.year == year, Budget.month == month)
        )
        budgets = list(budget_res.scalars().all())
        planned_by_cat: dict[str, Decimal] = {
            b.category.name: b.amount for b in budgets if b.category is not None
        }

        actual_rows = await self._sum_by_category(start, end, only_type=TransactionType.EXPENSE)
        actual_by_cat: dict[str, Decimal] = {
            r.name or "—": Decimal(str(r.total)) for r in actual_rows
        }

        all_cats = sorted(set(planned_by_cat) | set(actual_by_cat))
        rows = [
            BudgetVarianceRow(
                category=cat,
                planned=planned_by_cat.get(cat, Decimal("0")),
                actual=actual_by_cat.get(cat, Decimal("0")),
            )
            for cat in all_cats
        ]
        rows.sort(key=lambda r: r.actual, reverse=True)
        return BudgetVarianceReport(year=year, month=month, rows=rows)

    async def savings_rate(self, months: int = 12) -> list[SavingsRatePoint]:
        """One savings-rate data point per month, oldest → newest."""
        cashflow = await self.cashflow_last_n_months(months)
        return [
            SavingsRatePoint(year=m.year, month=m.month, income=m.income, expenses=m.expenses)
            for m in cashflow
        ]

    async def spending_by_category(
        self,
        start: datetime.date,
        end: datetime.date,
    ) -> SpendingByCategory:
        """Flat ranking of expense categories between [start, end)."""
        rows = await self._sum_by_category(start, end, only_type=TransactionType.EXPENSE)
        ranked = sorted(
            (
                CategoryAmount(category=r.name or "—", amount=Decimal(str(r.total)))
                for r in rows
            ),
            key=lambda c: c.amount,
            reverse=True,
        )
        return SpendingByCategory(start=start, end=end, rows=ranked)

    async def top_merchants(
        self,
        start: datetime.date,
        end: datetime.date,
        limit: int = 20,
    ) -> list[MerchantSpend]:
        """Top payees by expense total for the window."""
        result = await self.session.execute(
            select(
                Payee.name.label("name"),
                func.sum(Transaction.amount).label("total"),
                func.count(Transaction.id).label("cnt"),
            )
            .join(Payee, Transaction.payee_id == Payee.id)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by(Payee.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(limit)
        )
        return [
            MerchantSpend(
                name=row.name or "—",
                amount=Decimal(str(row.total)),
                count=int(row.cnt),
            )
            for row in result
        ]

    async def yoy_comparison(
        self,
        year: int,
        basis: TransactionType = TransactionType.EXPENSE,
    ) -> YoYComparison:
        """Monthly totals for `year` vs `year - 1`, for the chosen basis."""
        start = datetime.date(year - 1, 1, 1)
        end = datetime.date(year + 1, 1, 1)

        result = await self.session.execute(
            select(
                func.strftime("%Y", Transaction.date).label("yr"),
                func.strftime("%m", Transaction.date).label("mo"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.type == basis,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by("yr", "mo")
        )

        buckets: dict[tuple[int, int], Decimal] = {}
        for row in result:
            buckets[(int(row.yr), int(row.mo))] = Decimal(str(row.total))

        rows = [
            YoYRow(
                month=m,
                this_year=buckets.get((year, m), Decimal("0")),
                last_year=buckets.get((year - 1, m), Decimal("0")),
            )
            for m in range(1, 13)
        ]
        return YoYComparison(year=year, rows=rows, basis=basis.value)

    async def ytd_summary(self, year: int | None = None) -> YTDSummary:
        """Year-to-date income, expenses, net and top spending categories."""
        today = datetime.date.today()
        y = year or today.year
        start = datetime.date(y, 1, 1)
        # End is today (inclusive) for the current year, Jan 1 next year for past years.
        end = (
            today + datetime.timedelta(days=1)
            if y == today.year
            else datetime.date(y + 1, 1, 1)
        )

        totals = await self.session.execute(
            select(Transaction.type, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by(Transaction.type)
        )
        income = Decimal("0")
        expenses = Decimal("0")
        for row in totals:
            if row.type == TransactionType.INCOME:
                income = Decimal(str(row.total))
            elif row.type == TransactionType.EXPENSE:
                expenses = Decimal(str(row.total))

        cats = await self._sum_by_category(start, end, only_type=TransactionType.EXPENSE)
        ranked = sorted(
            (CategoryAmount(category=r.name or "—", amount=Decimal(str(r.total))) for r in cats),
            key=lambda c: c.amount,
            reverse=True,
        )
        return YTDSummary(
            year=y,
            income=income,
            expenses=expenses,
            top_expense_categories=ranked[:10],
        )

    async def largest_transactions(
        self,
        days: int = 90,
        limit: int = 50,
        tx_type: TransactionType | None = None,
    ) -> list[LargeTransaction]:
        """Top-N transactions by absolute amount in the last `days` days."""
        since = datetime.date.today() - datetime.timedelta(days=days)

        stmt = (
            select(Transaction)
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
            )
            .where(
                Transaction.date >= since,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .order_by(Transaction.amount.desc())
            .limit(limit)
        )
        if tx_type is not None:
            stmt = stmt.where(Transaction.type == tx_type)

        result = await self.session.execute(stmt)
        return [
            LargeTransaction(
                date=tx.date,
                account=tx.account.name if tx.account else "—",
                category=tx.category.name if tx.category else "—",
                description=tx.description or "",
                amount=tx.amount,
                type=tx.type,
            )
            for tx in result.scalars().all()
        ]

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _sum_by_category(
        self,
        start: datetime.date,
        end: datetime.date,
        only_type: TransactionType | None = None,
    ) -> list[Any]:
        """Return list of rows with .name (category), .type, .total columns.

        Uncategorised transactions are bucketed under a NULL name row so the
        caller can label them ("—" in the dataclasses).
        """
        stmt = (
            select(
                Category.name.label("name"),
                Transaction.type.label("type"),
                func.sum(Transaction.amount).label("total"),
            )
            .join(Category, Transaction.category_id == Category.id, isouter=True)
            .where(
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.is_internal_transfer == False,  # noqa: E712
            )
            .group_by(Category.name, Transaction.type)
        )
        if only_type is not None:
            stmt = stmt.where(Transaction.type == only_type)
        else:
            # Skip TRANSFER in category-based reports — transfers are
            # account-to-account movement, not income or expense.
            stmt = stmt.where(
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXPENSE])
            )

        result = await self.session.execute(stmt)
        return list(result.all())
