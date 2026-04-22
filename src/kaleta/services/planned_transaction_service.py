"""Service for planned (scheduled / recurring) transactions."""

from __future__ import annotations

import builtins
import calendar
import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate, PlannedTransactionUpdate

# ── Date arithmetic helpers ───────────────────────────────────────────────────


def _add_months(d: datetime.date, months: int) -> datetime.date:
    """Add `months` to date, clamping day to valid month range."""
    total = d.month + months
    year = d.year + (total - 1) // 12
    month = (total - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def _advance(d: datetime.date, frequency: RecurrenceFrequency, interval: int) -> datetime.date:
    """Return the next occurrence date by advancing `d` by one recurrence step."""
    if frequency == RecurrenceFrequency.DAILY:
        return d + datetime.timedelta(days=interval)
    if frequency == RecurrenceFrequency.WEEKLY:
        return d + datetime.timedelta(weeks=interval)
    if frequency == RecurrenceFrequency.BIWEEKLY:
        return d + datetime.timedelta(weeks=2 * interval)
    if frequency == RecurrenceFrequency.MONTHLY:
        return _add_months(d, interval)
    if frequency == RecurrenceFrequency.QUARTERLY:
        return _add_months(d, 3 * interval)
    if frequency == RecurrenceFrequency.YEARLY:
        try:
            return d.replace(year=d.year + interval)
        except ValueError:  # Feb 29 in non-leap year
            return d.replace(year=d.year + interval, day=28)
    return d  # ONCE — no advance


# ── Occurrence data ───────────────────────────────────────────────────────────


@dataclass
class PlannedOccurrence:
    date: datetime.date
    planned_id: int
    name: str
    amount: Decimal
    type: TransactionType
    account_id: int
    account_name: str
    category_name: str | None


@dataclass
class DayAggregate:
    """Per-day totals used by the Payment Calendar grid cell."""

    date: datetime.date
    inflow: Decimal
    outflow: Decimal
    occurrences: builtins.list[PlannedOccurrence]

    @property
    def net(self) -> Decimal:
        return self.inflow - self.outflow


@dataclass
class MonthGrid:
    """Calendar data for a single month plus a bucket of overdue items.

    Only days that have at least one occurrence are present in ``days``.
    ``overdue`` holds occurrences whose date fell in the trailing lookback
    window (default 30 days before the first of the month) — they are
    surfaced as a "needs attention" bucket in the calendar sidebar.
    """

    year: int
    month: int
    days: dict[datetime.date, DayAggregate]
    overdue: builtins.list[PlannedOccurrence]

    def total_inflow(self) -> Decimal:
        return sum((d.inflow for d in self.days.values()), Decimal("0"))

    def total_outflow(self) -> Decimal:
        return sum((d.outflow for d in self.days.values()), Decimal("0"))

    def total_net(self) -> Decimal:
        return self.total_inflow() - self.total_outflow()


# ── Service ───────────────────────────────────────────────────────────────────


class PlannedTransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _opts(self) -> builtins.list[Any]:
        return [
            selectinload(PlannedTransaction.account),
            selectinload(PlannedTransaction.category),
        ]

    async def list(self) -> builtins.list[PlannedTransaction]:
        stmt = (
            select(PlannedTransaction)
            .options(*self._opts())
            .order_by(PlannedTransaction.start_date, PlannedTransaction.name)
        )
        result = await self._session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def get(self, pt_id: int) -> PlannedTransaction | None:
        stmt = (
            select(PlannedTransaction).where(PlannedTransaction.id == pt_id).options(*self._opts())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: PlannedTransactionCreate) -> PlannedTransaction:
        pt = PlannedTransaction(**payload.model_dump())
        self._session.add(pt)
        await self._session.commit()
        return await self.get(pt.id)  # type: ignore[return-value]

    async def update(
        self, pt_id: int, payload: PlannedTransactionUpdate
    ) -> PlannedTransaction | None:
        pt = await self._session.get(PlannedTransaction, pt_id)
        if pt is None:
            return None
        for key, val in payload.model_dump(exclude_unset=True).items():
            setattr(pt, key, val)
        await self._session.commit()
        return await self.get(pt_id)

    async def delete(self, pt_id: int) -> bool:
        pt = await self._session.get(PlannedTransaction, pt_id)
        if pt is None:
            return False
        await self._session.delete(pt)
        await self._session.commit()
        return True

    async def toggle_active(self, pt_id: int) -> PlannedTransaction | None:
        pt = await self._session.get(PlannedTransaction, pt_id)
        if pt is None:
            return None
        pt.is_active = not pt.is_active
        await self._session.commit()
        return await self.get(pt_id)

    # ── Occurrence logic ──────────────────────────────────────────────────────

    def next_occurrence(
        self,
        pt: PlannedTransaction,
        after: datetime.date | None = None,
    ) -> datetime.date | None:
        """Compute the next occurrence of `pt` after `after` (defaults to today)."""
        today = after or datetime.date.today()
        current = pt.start_date

        if pt.frequency == RecurrenceFrequency.ONCE:
            if current > today and (pt.end_date is None or current <= pt.end_date):
                return current
            return None

        # Advance until strictly after today
        while current <= today:
            current = _advance(current, pt.frequency, pt.interval)

        if pt.end_date and current > pt.end_date:
            return None
        return current

    async def get_occurrences(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        account_id: int | None = None,
        active_only: bool = True,
    ) -> builtins.list[PlannedOccurrence]:
        """Generate every occurrence of planned transactions in [start_date, end_date]."""
        stmt = select(PlannedTransaction).options(*self._opts())
        if active_only:
            stmt = stmt.where(PlannedTransaction.is_active.is_(True))
        if account_id is not None:
            stmt = stmt.where(PlannedTransaction.account_id == account_id)

        result = await self._session.execute(stmt)
        planned_list = builtins.list(result.scalars().all())

        occurrences: builtins.list[PlannedOccurrence] = []
        for p in planned_list:
            # Skip plans that ended before our window
            if p.end_date and p.end_date < start_date:
                continue

            if p.frequency == RecurrenceFrequency.ONCE:
                if start_date <= p.start_date <= end_date:
                    occurrences.append(self._make_occurrence(p.start_date, p))
                continue

            # Fast-forward to the first occurrence >= start_date
            current = p.start_date
            while current < start_date:
                nxt = _advance(current, p.frequency, p.interval)
                if nxt <= current:  # safety: broken advance
                    break
                current = nxt
                if p.end_date and current > p.end_date:
                    break

            # Collect all occurrences within the window
            while current <= end_date:
                if p.end_date and current > p.end_date:
                    break
                if current >= start_date:
                    occurrences.append(self._make_occurrence(current, p))
                current = _advance(current, p.frequency, p.interval)

        occurrences.sort(key=lambda o: o.date)
        return occurrences

    async def grid_for_month(
        self,
        year: int,
        month: int,
        *,
        account_id: int | None = None,
        active_only: bool = True,
        overdue_window_days: int = 30,
    ) -> MonthGrid:
        """Return per-day aggregates for the month plus overdue bucket.

        Overdue items are occurrences whose date falls within
        ``[month_start - overdue_window_days, month_start)``. A future
        reconciliation flow (not in this version) will narrow this to
        un-reconciled items only.
        """
        first = datetime.date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        last = datetime.date(year, month, last_day)

        occurrences = await self.get_occurrences(
            first,
            last,
            account_id=account_id,
            active_only=active_only,
        )

        days: dict[datetime.date, DayAggregate] = {}
        for occ in occurrences:
            cell = days.get(occ.date)
            if cell is None:
                cell = DayAggregate(
                    date=occ.date,
                    inflow=Decimal("0"),
                    outflow=Decimal("0"),
                    occurrences=[],
                )
                days[occ.date] = cell
            amt = abs(occ.amount)
            if occ.type == TransactionType.INCOME:
                cell.inflow += amt
            elif occ.type == TransactionType.EXPENSE:
                cell.outflow += amt
            cell.occurrences.append(occ)

        overdue_start = first - datetime.timedelta(days=overdue_window_days)
        overdue_end = first - datetime.timedelta(days=1)
        overdue: builtins.list[PlannedOccurrence] = []
        if overdue_end >= overdue_start:
            overdue = await self.get_occurrences(
                overdue_start,
                overdue_end,
                account_id=account_id,
                active_only=active_only,
            )

        return MonthGrid(year=year, month=month, days=days, overdue=overdue)

    def _make_occurrence(self, d: datetime.date, p: PlannedTransaction) -> PlannedOccurrence:
        return PlannedOccurrence(
            date=d,
            planned_id=p.id,
            name=p.name,
            amount=p.amount,
            type=p.type,
            account_id=p.account_id,
            account_name=p.account.name if p.account else f"Account {p.account_id}",
            category_name=p.category.name if p.category else None,
        )
