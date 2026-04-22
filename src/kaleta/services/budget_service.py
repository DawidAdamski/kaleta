from __future__ import annotations

import builtins
import calendar
import datetime
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.budget import Budget
from kaleta.models.category import Category, CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.budget import BudgetCreate, BudgetUpdate

REALIZATION_WARNING_THRESHOLD_PCT: float = 5.0


class RealizationStatus(str, Enum):  # noqa: UP042
    ON_TRACK = "on_track"
    WARNING = "warning"
    OVER = "over"


@dataclass
class CategoryBudgetSummary:
    category_id: int
    category_name: str
    budget_amount: Decimal
    actual_amount: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.budget_amount - self.actual_amount

    @property
    def percent_used(self) -> float:
        if self.budget_amount == 0:
            return 0.0
        return float(self.actual_amount / self.budget_amount * 100)

    @property
    def over_budget(self) -> bool:
        return self.actual_amount > self.budget_amount


@dataclass
class CategoryRealization:
    category_id: int
    category_name: str
    parent_id: int | None
    parent_name: str | None
    planned: Decimal
    actual: Decimal
    elapsed_pct: float
    used_pct: float

    @property
    def remaining(self) -> Decimal:
        return self.planned - self.actual

    @property
    def status(self) -> RealizationStatus:
        if self.used_pct > 100:
            return RealizationStatus.OVER
        if self.used_pct > self.elapsed_pct + REALIZATION_WARNING_THRESHOLD_PCT:
            return RealizationStatus.WARNING
        return RealizationStatus.ON_TRACK

    @property
    def pace_delta(self) -> float:
        """used_pct minus elapsed_pct — positive means ahead of pace (worse)."""
        return self.used_pct - self.elapsed_pct


class BudgetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self, month: int | None = None, year: int | None = None
    ) -> builtins.list[Budget]:
        stmt = (
            select(Budget)
            .options(selectinload(Budget.category))
            .order_by(Budget.year.desc(), Budget.month.desc())
        )
        if month is not None:
            stmt = stmt.where(
                Budget.month == month, Budget.year == (year or datetime.date.today().year)
            )
        result = await self.session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def list_for_year(self, year: int) -> builtins.list[Budget]:
        """Return all budget entries for every month of the given year."""
        result = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(Budget.year == year)
            .order_by(Budget.month)
        )
        return builtins.list(result.scalars().all())

    async def get(self, budget_id: int) -> Budget | None:
        return await self.session.get(Budget, budget_id, options=[selectinload(Budget.category)])

    async def get_by_category_period(
        self, category_id: int, month: int, year: int
    ) -> Budget | None:
        result = await self.session.execute(
            select(Budget).where(
                Budget.category_id == category_id,
                Budget.month == month,
                Budget.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: BudgetCreate) -> Budget:
        budget = Budget(**data.model_dump())
        self.session.add(budget)
        await self.session.commit()
        await self.session.refresh(budget)
        return budget

    async def upsert(self, data: BudgetCreate) -> Budget:
        """Create or update a budget for the given category+period."""
        existing = await self.get_by_category_period(data.category_id, data.month, data.year)
        if existing:
            existing.amount = data.amount
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        return await self.create(data)

    async def bulk_upsert(self, entries: builtins.list[BudgetCreate]) -> int:
        """Create-or-update many Budget rows in a single transaction.

        Returns the number of rows written. Entries are keyed by
        (category_id, month, year); duplicates in the input sum together.
        """
        if not entries:
            return 0

        # Sum duplicates coming from multiple lines targeting the same
        # (category, month, year) triplet — callers may produce them.
        merged: dict[tuple[int, int, int], Decimal] = {}
        for e in entries:
            k = (e.category_id, e.month, e.year)
            merged[k] = merged.get(k, Decimal("0")) + e.amount

        year = next(iter(merged))[2]
        existing_rows = await self.session.execute(
            select(Budget).where(Budget.year == year)
        )
        existing_map: dict[tuple[int, int, int], Budget] = {
            (b.category_id, b.month, b.year): b for b in existing_rows.scalars().all()
        }

        for key, amount in merged.items():
            row = existing_map.get(key)
            if row is not None:
                row.amount = amount
            else:
                cat_id, month, yr = key
                self.session.add(
                    Budget(category_id=cat_id, amount=amount, month=month, year=yr)
                )
        await self.session.commit()
        return len(merged)

    async def list_for_month(self, year: int, month: int) -> builtins.list[Budget]:
        """Return all budget entries for a single (year, month)."""
        result = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(Budget.year == year, Budget.month == month)
            .order_by(Budget.category_id)
        )
        return builtins.list(result.scalars().all())

    async def copy_forward(
        self,
        from_year: int,
        from_month: int,
        to_year: int,
        to_month: int,
        *,
        overwrite: bool = False,
    ) -> int:
        """Copy every budget row from one month into the next.

        When ``overwrite`` is False (default), categories that already have
        a budget for ``(to_year, to_month)`` keep their existing amount —
        matches the "Allocate *new* month" intent. Returns the number of
        rows actually written (created or updated).
        """
        src = await self.list_for_month(from_year, from_month)
        if not src:
            return 0

        existing = await self.list_for_month(to_year, to_month)
        existing_cats = {b.category_id for b in existing}

        written = 0
        for src_row in src:
            if src_row.category_id in existing_cats and not overwrite:
                continue
            await self.upsert(
                BudgetCreate(
                    category_id=src_row.category_id,
                    amount=src_row.amount,
                    month=to_month,
                    year=to_year,
                )
            )
            written += 1
        return written

    async def update(self, budget_id: int, data: BudgetUpdate) -> Budget | None:
        budget = await self.get(budget_id)
        if budget is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(budget, field, value)
        await self.session.commit()
        await self.session.refresh(budget)
        return budget

    async def delete(self, budget_id: int) -> bool:
        budget = await self.get(budget_id)
        if budget is None:
            return False
        await self.session.delete(budget)
        await self.session.commit()
        return True

    async def delete_all_for_category_year(self, category_id: int, year: int) -> int:
        """Delete all budget entries for a category in a year. Returns count deleted."""
        result = await self.session.execute(
            select(Budget).where(Budget.category_id == category_id, Budget.year == year)
        )
        budgets = builtins.list(result.scalars().all())
        for b in budgets:
            await self.session.delete(b)
        await self.session.commit()
        return len(budgets)

    async def monthly_summary(self, month: int, year: int) -> builtins.list[CategoryBudgetSummary]:
        """Budget vs actual spending for a single month."""
        last_day = calendar.monthrange(year, month)[1]
        start = datetime.date(year, month, 1)
        end = datetime.date(year, month, last_day)
        return await self.range_summary(start, end)

    async def realization_for_month(
        self,
        year: int,
        month: int,
        *,
        today: datetime.date | None = None,
    ) -> builtins.list[CategoryRealization]:
        """Per-category realization (plan vs actual + pacing) for a single month.

        Rows are returned for every expense category that has either a budget
        entry in the month or actual spending in it. Sorted worst-pace first
        (over-budget → warning → on-track; within each bucket, higher
        pace_delta first).
        """
        if today is None:
            today = datetime.date.today()

        last_day = calendar.monthrange(year, month)[1]
        month_start = datetime.date(year, month, 1)
        month_end = datetime.date(year, month, last_day)

        if today < month_start:
            elapsed_pct = 0.0
        elif today > month_end:
            elapsed_pct = 100.0
        else:
            elapsed_pct = (today.day / last_day) * 100.0

        budget_rows = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category).selectinload(Category.parent))
            .where(Budget.month == month, Budget.year == year)
        )
        budgets = builtins.list(budget_rows.scalars().all())
        planned: dict[int, Decimal] = {b.category_id: b.amount for b in budgets}

        parent_lookup: dict[int, tuple[int | None, str | None, str]] = {
            b.category_id: (
                b.category.parent_id,
                b.category.parent.name if b.category.parent else None,
                b.category.name,
            )
            for b in budgets
        }

        actuals_rows = await self.session.execute(
            select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.category_id.isnot(None),
            )
            .group_by(Transaction.category_id)
        )
        actuals: dict[int, Decimal] = {row.category_id: row.total for row in actuals_rows}

        missing_ids = [cid for cid in actuals if cid not in parent_lookup]
        if missing_ids:
            cats_result = await self.session.execute(
                select(Category)
                .options(selectinload(Category.parent))
                .where(Category.id.in_(missing_ids), Category.type == CategoryType.EXPENSE)
            )
            for cat in cats_result.scalars().all():
                parent_lookup[cat.id] = (
                    cat.parent_id,
                    cat.parent.name if cat.parent else None,
                    cat.name,
                )

        rows: builtins.list[CategoryRealization] = []
        for cat_id, (parent_id, parent_name, name) in parent_lookup.items():
            planned_amt = planned.get(cat_id, Decimal("0"))
            actual_amt = actuals.get(cat_id, Decimal("0"))
            used_pct = (
                float(actual_amt / planned_amt * 100) if planned_amt > 0 else (
                    float("inf") if actual_amt > 0 else 0.0
                )
            )
            rows.append(
                CategoryRealization(
                    category_id=cat_id,
                    category_name=name,
                    parent_id=parent_id,
                    parent_name=parent_name,
                    planned=planned_amt,
                    actual=actual_amt,
                    elapsed_pct=elapsed_pct,
                    used_pct=used_pct,
                )
            )

        status_order = {
            RealizationStatus.OVER: 0,
            RealizationStatus.WARNING: 1,
            RealizationStatus.ON_TRACK: 2,
        }
        rows.sort(key=lambda r: (status_order[r.status], -r.pace_delta, r.category_name))
        return rows

    async def range_summary(
        self, start: datetime.date, end: datetime.date
    ) -> builtins.list[CategoryBudgetSummary]:
        """Aggregate budget vs actual spending over an arbitrary date range.

        Includes:
        - All expense categories with a budget entry in the period.
        - All expense categories with actual spending in the period (even if unbudgeted).
        Budget amount is 0 for unbudgeted categories.
        """
        start_key = start.year * 12 + start.month
        end_key = end.year * 12 + end.month
        budget_key = Budget.year * 12 + Budget.month

        # Load budget rows
        budget_result = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(budget_key >= start_key, budget_key <= end_key)
        )
        budgets = list(budget_result.scalars().all())

        budget_totals: dict[int, Decimal] = {}
        category_names: dict[int, str] = {}
        for b in budgets:
            budget_totals[b.category_id] = budget_totals.get(b.category_id, Decimal("0")) + b.amount
            category_names[b.category_id] = b.category.name

        # Load ALL expense category names (for unbudgeted categories with spending)
        cats_result = await self.session.execute(
            select(Category.id, Category.name).where(Category.type == CategoryType.EXPENSE)
        )
        all_expense_cats: dict[int, str] = {row.id: row.name for row in cats_result}

        # Load actual expenses in period (all expense categories)
        actuals_result = await self.session.execute(
            select(Transaction.category_id, func.sum(Transaction.amount).label("total"))
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.category_id.isnot(None),
            )
            .group_by(Transaction.category_id)
        )
        actuals: dict[int, Decimal] = {row.category_id: row.total for row in actuals_result}

        # Union: categories with a budget OR with actual spending
        all_cat_ids = set(budget_totals.keys()) | {
            cid for cid in actuals if cid in all_expense_cats
        }

        return sorted(
            builtins.list(
                [
                    CategoryBudgetSummary(
                        category_id=cat_id,
                        category_name=category_names.get(cat_id)
                        or all_expense_cats.get(cat_id, "Unknown"),
                        budget_amount=budget_totals.get(cat_id, Decimal("0")),
                        actual_amount=actuals.get(cat_id, Decimal("0")),
                    )
                    for cat_id in all_cat_ids
                ]
            ),
            key=lambda s: s.category_name,
        )

    async def actuals_by_category_month(self, year: int) -> dict[tuple[int, int], Decimal]:
        """Return {(category_id, month): actual_amount} for expense transactions."""
        result = await self.session.execute(
            select(
                Transaction.category_id,
                extract("month", Transaction.date).label("month"),
                func.sum(Transaction.amount).label("total"),
            )
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.date >= datetime.date(year, 1, 1),
                Transaction.date <= datetime.date(year, 12, 31),
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.category_id.isnot(None),
            )
            .group_by(Transaction.category_id, extract("month", Transaction.date))
        )
        return {(int(row.category_id), int(row.month)): row.total for row in result}
