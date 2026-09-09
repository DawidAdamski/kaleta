# SPDX-License-Identifier: AGPL-3.0-or-later
"""Smooth irregular income into one fixed monthly "salary".

The panel behind this service answers a single question for a freelancer or
contractor: *how much can I safely pay myself every month?* The answer comes
from a window of recent **complete** months — the running month is always
partial and would drag the proposal down — reduced to a conservative
statistic (worst month by default). Whatever a month earns above the salary
accumulates as a buffer that carries the lean months.

Nothing here schedules or posts money. Accepting a proposal creates one
ordinary recurring planned transaction through
:class:`~kaleta.services.planned_transaction_service.PlannedTransactionService`.
"""

from __future__ import annotations

import calendar
import datetime
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.account import Account
from kaleta.models.planned_transaction import PlannedTransaction, RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.salary import (
    BufferPoint,
    MonthlyIncome,
    SalaryBasis,
    SalaryPlanCreate,
    SalaryProposal,
)
from kaleta.services.planned_transaction_service import PlannedTransactionService

#: Fewer complete months than this and the window says nothing about
#: variability — the panel shows a hint instead of a proposal.
MIN_HISTORY_MONTHS = 3

#: Default look-back, in complete months.
DEFAULT_WINDOW_MONTHS = 12

_CENT = Decimal("0.01")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return ``(year, month)`` moved by ``delta`` months (delta may be negative)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _month_end(year: int, month: int) -> datetime.date:
    return datetime.date(year, month, calendar.monthrange(year, month)[1])


def _percentile(values: list[Decimal], q: Decimal) -> Decimal:
    """Linear-interpolated percentile of ``values`` (``q`` in ``[0, 1]``).

    Matches the usual "linear" definition: the sample is sorted, ``q`` picks a
    fractional rank in ``[0, n-1]``, and neighbouring samples are blended.
    """
    if not values:
        return Decimal("0.00")
    ordered = sorted(values)
    if len(ordered) == 1:
        return _quantize(ordered[0])
    position = q * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - Decimal(lower)
    return _quantize(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction)


def _project_buffer(months: list[MonthlyIncome], salary: Decimal) -> list[BufferPoint]:
    """Replay the window: what the buffer would hold after each month."""
    running = Decimal("0.00")
    points: list[BufferPoint] = []
    for entry in months:
        surplus = _quantize(entry.total - salary)
        running = _quantize(running + surplus)
        points.append(
            BufferPoint(
                year=entry.year,
                month=entry.month,
                income=_quantize(entry.total),
                surplus=surplus,
                buffer=running,
            )
        )
    return points


class SalaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Income window ─────────────────────────────────────────────────────

    async def income_by_month(
        self,
        *,
        window_months: int = DEFAULT_WINDOW_MONTHS,
        today: datetime.date | None = None,
    ) -> tuple[list[MonthlyIncome], list[str]]:
        """Monthly non-transfer income over the window, plus the currencies seen.

        The series is oldest-first and starts at the **first month that earned
        anything** inside the window: leading empty months are absence of data,
        not a zero-income month. Gaps and trailing months after that first
        earning month stay in as zeros — a dry month is real information.
        """
        if window_months < 1:
            raise ValidationError("Income window must span at least one month.")

        today = today or datetime.date.today()
        last_year, last_month = _shift_month(today.year, today.month, -1)
        first_year, first_month = _shift_month(last_year, last_month, -(window_months - 1))
        start = datetime.date(first_year, first_month, 1)
        end = _month_end(last_year, last_month)

        result = await self.session.execute(
            select(Transaction.date, Transaction.amount, Account.currency)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.type == TransactionType.INCOME,
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= start,
                Transaction.date <= end,
            )
        )

        totals: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0.00"))
        currencies: set[str] = set()
        for row_date, amount, currency in result:
            totals[(row_date.year, row_date.month)] += Decimal(amount)
            currencies.add(currency)

        if not totals:
            return [], []

        earliest = min(totals)
        months: list[MonthlyIncome] = []
        year, month = earliest
        while (year, month) <= (last_year, last_month):
            months.append(
                MonthlyIncome(year=year, month=month, total=_quantize(totals[(year, month)]))
            )
            year, month = _shift_month(year, month, 1)
        return months, sorted(currencies)

    # ── Proposal ──────────────────────────────────────────────────────────

    async def propose(
        self,
        *,
        window_months: int = DEFAULT_WINDOW_MONTHS,
        basis: SalaryBasis = SalaryBasis.WORST,
        override: Decimal | None = None,
        today: datetime.date | None = None,
    ) -> SalaryProposal:
        """Income variability of the window and the salary it supports.

        ``override`` replaces the statistic chosen by ``basis`` — the buffer
        projection is replayed against whatever amount actually applies.
        """
        if override is not None and override < 0:
            raise ValidationError("Salary override cannot be negative.")

        months, currencies = await self.income_by_month(window_months=window_months, today=today)
        has_enough_history = len(months) >= MIN_HISTORY_MONTHS
        totals = [m.total for m in months]

        worst = _quantize(min(totals)) if totals else Decimal("0.00")
        best = _quantize(max(totals)) if totals else Decimal("0.00")
        median = _percentile(totals, Decimal("0.5"))
        p25 = _percentile(totals, Decimal("0.25"))
        by_basis = {SalaryBasis.WORST: worst, SalaryBasis.P25: p25, SalaryBasis.MEDIAN: median}

        if override is not None:
            salary = _quantize(override)
        elif has_enough_history:
            salary = by_basis[basis]
        else:
            # Too short a window to say anything — no proposal, no projection.
            salary = Decimal("0.00")

        projection = _project_buffer(months, salary) if salary > 0 else []

        return SalaryProposal(
            window_months=window_months,
            months=months,
            worst=worst,
            best=best,
            median=median,
            p25=p25,
            basis=basis,
            salary=salary,
            projection=projection,
            has_enough_history=has_enough_history,
            currencies=currencies,
        )

    # ── Accepting a proposal ──────────────────────────────────────────────

    async def create_salary_plan(self, payload: SalaryPlanCreate) -> PlannedTransaction:
        """Create the monthly self-transfer that pays the salary out.

        The planned-transactions model carries a single account, so the target
        account lives in the description — enough for the Payment Calendar to
        read, and no new scheduling machinery.
        """
        if payload.from_account_id == payload.to_account_id:
            raise ValidationError("Salary source and target accounts must differ.")

        accounts = (
            (
                await self.session.execute(
                    select(Account).where(
                        Account.id.in_([payload.from_account_id, payload.to_account_id])
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {a.id: a for a in accounts}
        for account_id in (payload.from_account_id, payload.to_account_id):
            if account_id not in by_id:
                raise NotFoundError(f"Account {account_id} not found.")

        source = by_id[payload.from_account_id]
        target = by_id[payload.to_account_id]
        return await PlannedTransactionService(self.session).create(
            PlannedTransactionCreate(
                name=payload.name,
                amount=payload.amount,
                type=TransactionType.TRANSFER,
                account_id=payload.from_account_id,
                description=f"{source.name} → {target.name}",
                frequency=RecurrenceFrequency.MONTHLY,
                interval=1,
                start_date=payload.start_date,
                is_active=True,
            )
        )
