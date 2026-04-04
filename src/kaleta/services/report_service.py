from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account
from kaleta.models.transaction import Transaction, TransactionType


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


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def total_balance(self) -> Decimal:
        result = await self.session.execute(select(func.sum(Account.balance)))
        val = result.scalar()
        return Decimal(str(val)) if val else Decimal("0.00")

    async def current_month_summary(self) -> tuple[Decimal, Decimal]:
        """Returns (income, expenses) for the current calendar month."""
        today = datetime.date.today()
        start = today.replace(day=1)
        if today.month == 12:
            end = datetime.date(today.year + 1, 1, 1)
        else:
            end = datetime.date(today.year, today.month + 1, 1)

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
        """Aggregate income and expenses per calendar month for the last n months."""
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

        # Collect into dict keyed by (year, month)
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
