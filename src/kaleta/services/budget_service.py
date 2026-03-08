from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.budget import Budget
from kaleta.models.category import Category, CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.budget import BudgetCreate, BudgetUpdate


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


class BudgetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, month: int | None = None, year: int | None = None) -> list[Budget]:
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
        return list(result.scalars().all())

    async def list_for_year(self, year: int) -> list[Budget]:
        """Return all budget entries for every month of the given year."""
        result = await self.session.execute(
            select(Budget)
            .options(selectinload(Budget.category))
            .where(Budget.year == year)
            .order_by(Budget.month)
        )
        return list(result.scalars().all())

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
        budgets = list(result.scalars().all())
        for b in budgets:
            await self.session.delete(b)
        await self.session.commit()
        return len(budgets)

    async def monthly_summary(self, month: int, year: int) -> list[CategoryBudgetSummary]:
        """Budget vs actual spending for a single month."""
        import calendar

        last_day = calendar.monthrange(year, month)[1]
        start = datetime.date(year, month, 1)
        end = datetime.date(year, month, last_day)
        return await self.range_summary(start, end)

    async def range_summary(
        self, start: datetime.date, end: datetime.date
    ) -> list[CategoryBudgetSummary]:
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
            [
                CategoryBudgetSummary(
                    category_id=cat_id,
                    category_name=category_names.get(cat_id)
                    or all_expense_cats.get(cat_id, "Unknown"),
                    budget_amount=budget_totals.get(cat_id, Decimal("0")),
                    actual_amount=actuals.get(cat_id, Decimal("0")),
                )
                for cat_id in all_cat_ids
            ],
            key=lambda s: s.category_name,
        )

    async def actuals_by_category_month(self, year: int) -> dict[tuple[int, int], Decimal]:
        """Return {(category_id, month): actual_amount} for expense transactions in the given year.
        """
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
