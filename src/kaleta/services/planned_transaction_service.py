# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service for planned (scheduled / recurring) transactions."""

from __future__ import annotations

import builtins
import calendar
import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import NotFoundError
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate, PlannedTransactionUpdate
from kaleta.services.transaction_service import TransactionService

logger = logging.getLogger(__name__)

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
    category_id: int | None
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
        *,
        exclude_posted: bool = False,
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

        if exclude_posted and occurrences:
            posted = await self._posted_keys({(o.planned_id, o.date) for o in occurrences})
            occurrences = [o for o in occurrences if (o.planned_id, o.date) not in posted]

        occurrences.sort(key=lambda o: o.date)
        return occurrences

    # ── Upcoming rows for the ledger ──────────────────────────────────────────

    @staticmethod
    def upcoming_window(
        days: int,
        *,
        today: datetime.date,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
    ) -> tuple[datetime.date, datetime.date] | None:
        """The stretch of days to look ahead over, or ``None`` for no window.

        The window starts today — what fell before it either reached the ledger
        as a real row or is overdue, which the Payment Calendar owns — and is
        clipped to whatever date range the caller has filtered down to, so a
        range that ends in the past opens no window at all.
        """
        if days <= 0:
            return None
        start = max(today, date_from) if date_from else today
        end = today + datetime.timedelta(days=days)
        if date_to:
            end = min(end, date_to)
        return None if start > end else (start, end)

    async def upcoming_for_ledger(
        self,
        start_date: datetime.date,
        end_date: datetime.date,
        *,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
    ) -> builtins.list[PlannedOccurrence]:
        """Occurrences in ``[start_date, end_date]`` that the ledger should show.

        The same filters the ledger applies to its actuals, applied to the
        occurrences too — a list narrowed to one account must not grow a
        planned row belonging to another. Already-posted occurrences are left
        out: the ledger is holding the real transaction for them, and a row
        promising money that has already moved would be counted twice by eye.
        """
        if start_date > end_date:
            return []

        occurrences = await self.get_occurrences(
            start_date,
            end_date,
            active_only=True,
            exclude_posted=True,
        )

        needle = (search or "").strip().lower()
        return [
            occ
            for occ in occurrences
            if (not account_ids or occ.account_id in account_ids)
            and (not category_ids or occ.category_id in category_ids)
            and (not tx_types or occ.type in tx_types)
            and (not needle or needle in occ.name.lower())
        ]

    @staticmethod
    def planned_row_key(planned_id: int, occurrence_date: datetime.date) -> str:
        """The id an upcoming row carries: ``planned:<plan id>:<ISO date>``.

        A string, so it can never be mistaken for a transaction id by anything
        that deletes or totals by id. Built and parsed in one place, because
        the browser hands the key straight back on a click.
        """
        return f"planned:{planned_id}:{occurrence_date.isoformat()}"

    @staticmethod
    def parse_planned_row_key(row_key: object) -> tuple[int, datetime.date] | None:
        """Split a planned row's key back into its parts, or ``None``.

        The browser sends back whatever the row carried, so a key that is not
        one of ours — a stale event, a hand-edited payload — has to come back
        as ``None`` rather than raise inside a click handler.
        """
        parts = row_key.split(":") if isinstance(row_key, str) else []
        if len(parts) != 3 or parts[0] != "planned":
            return None
        try:
            return int(parts[1]), datetime.date.fromisoformat(parts[2])
        except ValueError:
            return None

    @staticmethod
    def build_upcoming_rows(
        occurrences: builtins.list[PlannedOccurrence],
        today: datetime.date,
    ) -> builtins.list[dict[str, Any]]:
        """Shape occurrences like ledger rows so both can share one table.

        The row carries everything the table's body slot reads, plus the marks
        that tell a promise from a fact: ``is_planned``, the plan behind it and
        how many days out it falls. The id is a string key of its own — a
        planned row must never collide with a transaction id, because the
        selection bar's delete button works off those ids.
        """
        rows: builtins.list[dict[str, Any]] = []
        for occ in occurrences:
            rows.append(
                {
                    "id": PlannedTransactionService.planned_row_key(occ.planned_id, occ.date),
                    "planned_id": occ.planned_id,
                    "is_planned": True,
                    "days_ahead": (occ.date - today).days,
                    "date": str(occ.date),
                    "date_short": occ.date.strftime("%d.%m"),
                    "account": occ.account_name,
                    "description": occ.name[:55],
                    "notes": "",
                    "has_notes": False,
                    "category": occ.category_name or "—",
                    "has_splits": False,
                    "split_count": 0,
                    "split_tooltip": "",
                    "type": occ.type.value,
                    "amount": TransactionService.format_signed_amount(occ.amount, occ.type),
                    "amount_value": str(TransactionService.signed_amount(occ.amount, occ.type)),
                    "tags": "",
                    "tags_data": [],
                    "sep_label": "",
                }
            )
        return rows

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
        ``[month_start - overdue_window_days, month_start)`` and have not
        yet been posted to the ledger.
        """
        first = datetime.date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        last = datetime.date(year, month, last_day)

        occurrences = await self.get_occurrences(
            first,
            last,
            account_id=account_id,
            active_only=active_only,
            exclude_posted=True,
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
                exclude_posted=True,
            )

        return MonthGrid(year=year, month=month, days=days, overdue=overdue)

    async def post_occurrence(
        self,
        planned_id: int,
        occurrence_date: datetime.date,
    ) -> Transaction:
        """Post one planned occurrence as a real transaction (idempotent)."""
        tx = await self._ensure_posted(planned_id, occurrence_date)
        await self._session.commit()
        fetched = await self._get_transaction(tx.id)
        assert fetched is not None
        return fetched

    async def post_due(
        self,
        *,
        as_of: datetime.date | None = None,
        lookback_days: int = 30,
        planned_id: int | None = None,
    ) -> builtins.list[Transaction]:
        """Post every unposted occurrence in ``[as_of - lookback, as_of]``.

        Idempotent: already-posted occurrences are skipped / returned as-is.
        When ``planned_id`` is set, only that plan is considered.
        """
        as_of = as_of or datetime.date.today()
        start = as_of - datetime.timedelta(days=lookback_days)
        occurrences = await self.get_occurrences(
            start,
            as_of,
            active_only=True,
            exclude_posted=True,
        )
        if planned_id is not None:
            occurrences = [o for o in occurrences if o.planned_id == planned_id]

        results: builtins.list[Transaction] = []
        for occ in occurrences:
            results.append(await self.post_occurrence(occ.planned_id, occ.date))
        logger.info(
            "Posted %s due planned occurrence(s) (as_of=%s, lookback=%s)",
            len(results),
            as_of.isoformat(),
            lookback_days,
        )
        return results

    async def _ensure_posted(
        self,
        planned_id: int,
        occurrence_date: datetime.date,
    ) -> Transaction:
        """Create or return the ledger row for ``(planned_id, occurrence_date)``."""
        existing = await self._find_posted(planned_id, occurrence_date)
        if existing is not None:
            return existing

        pt = await self.get(planned_id)
        if pt is None:
            raise NotFoundError(f"Planned transaction {planned_id} not found")

        description = (pt.description or pt.name or "").strip()
        tx = Transaction(
            account_id=pt.account_id,
            category_id=pt.category_id,
            amount=abs(pt.amount),
            type=pt.type,
            date=occurrence_date,
            description=description,
            is_internal_transfer=False,
            is_split=False,
            planned_transaction_id=pt.id,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(tx)
                await self._session.flush()
        except IntegrityError:
            existing = await self._find_posted(planned_id, occurrence_date)
            if existing is not None:
                return existing
            raise
        return tx

    async def _find_posted(
        self,
        planned_id: int,
        occurrence_date: datetime.date,
    ) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.planned_transaction_id == planned_id,
            Transaction.date == occurrence_date,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_transaction(self, tx_id: int) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.id == tx_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _posted_keys(
        self,
        candidates: builtins.set[tuple[int, datetime.date]],
    ) -> builtins.set[tuple[int, datetime.date]]:
        if not candidates:
            return set()
        stmt = select(Transaction.planned_transaction_id, Transaction.date).where(
            Transaction.planned_transaction_id.is_not(None),
            tuple_(Transaction.planned_transaction_id, Transaction.date).in_(candidates),
        )
        result = await self._session.execute(stmt)
        return {(int(pid), d) for pid, d in result.all() if pid is not None}

    def _make_occurrence(self, d: datetime.date, p: PlannedTransaction) -> PlannedOccurrence:
        return PlannedOccurrence(
            date=d,
            planned_id=p.id,
            name=p.name,
            amount=p.amount,
            type=p.type,
            account_id=p.account_id,
            account_name=p.account.name if p.account else f"Account {p.account_id}",
            category_id=p.category_id,
            category_name=p.category.name if p.category else None,
        )
