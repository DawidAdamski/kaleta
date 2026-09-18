# SPDX-License-Identifier: AGPL-3.0-or-later
"""What-if scenarios: deltas laid over a baseline forecast.

This is **not** a second forecasting engine. The baseline comes from
``forecast_service`` exactly as the Forecast page draws it, and everything
here is post-processing: each delta is compiled into dated cash events and
handed to :func:`forecast_service.apply_scenarios`, the same function the
Forecast page's own scenario pins already use.

Compiling to one-off events is what keeps a recurring bill honest. A
"new 300 zł subscription from March" is thirty-odd separate withdrawals on
the days they happen, not a slope drawn through them, so the line steps
where the money actually leaves.
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.schemas.scenario import (
    ScenarioDelta,
    ScenarioDeltaKind,
    ScenarioVerdict,
    occurrences_per_month,
)
from kaleta.services.forecast_service import (
    ForecastResult,
    ScenarioShift,
    apply_scenarios,
)
from kaleta.services.reserve_fund_service import (
    TRAILING_WINDOW_DAYS,
    TRAILING_WINDOW_MONTHS,
    ReserveFundService,
)

_CENTS = Decimal("0.01")
_TENTHS = Decimal("0.1")

#: The horizon the panel offers, in months. The plan's open question settled
#: on matching the forecast presets rather than inventing a third scale.
DEFAULT_HORIZON_MONTHS = 12
MAX_HORIZON_MONTHS = 24

#: Days to a month, for turning a horizon into the days the forecaster counts
#: in. Approximate on purpose: the horizon is a reading window, not a date.
_DAYS_PER_MONTH = 30


def horizon_days(months: int) -> int:
    """The forecast horizon in days, for a horizon asked for in months."""
    return max(1, min(months, MAX_HORIZON_MONTHS)) * _DAYS_PER_MONTH


#: A guard on compiling a cadence into dated events. A daily delta over a
#: two-year horizon is ~730 events, so this only trips on a cadence that
#: repeats faster than the forecast has days to put it on.
_MAX_OCCURRENCES = 1000


def _add_months(day: datetime.date, months: int) -> datetime.date:
    """Shift by whole months, clamping to the end of a shorter one."""
    total = day.month - 1 + months
    year = day.year + total // 12
    month = total % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last))


def _step(day: datetime.date, cadence: RecurrenceFrequency) -> datetime.date | None:
    """The next date *cadence* fires after *day*, or ``None`` if it never does."""
    match cadence:
        case RecurrenceFrequency.DAILY:
            return day + datetime.timedelta(days=1)
        case RecurrenceFrequency.WEEKLY:
            return day + datetime.timedelta(weeks=1)
        case RecurrenceFrequency.BIWEEKLY:
            return day + datetime.timedelta(weeks=2)
        case RecurrenceFrequency.MONTHLY:
            return _add_months(day, 1)
        case RecurrenceFrequency.QUARTERLY:
            return _add_months(day, 3)
        case RecurrenceFrequency.YEARLY:
            return _add_months(day, 12)
        case RecurrenceFrequency.ONCE:
            return None


def monthly_amount(delta: ScenarioDelta, monthly_income: Decimal) -> Decimal:
    """What *delta* is worth in a month, with a percentage read against income.

    The one place that resolution happens. Written twice — once for the chart
    and once for the "Monthly cashflow" figure — it would eventually give the
    two of them different answers to the same question.
    """
    if delta.amount is not None:
        return delta.amount
    return monthly_income * (delta.percent or Decimal("0")) / Decimal("100")


def compile_delta(
    delta: ScenarioDelta,
    *,
    monthly_income: Decimal,
    horizon_start: datetime.date,
    horizon_end: datetime.date,
) -> list[ScenarioShift]:
    """One delta's dated cash events, in the order they happen.

    *monthly_income* is what a percentage income change is read against: the
    balance series records what is left over, never what came in, so a
    "−30%" has no meaning without it.

    *horizon_start* is the forecast's **first** point, and the delta starts no
    earlier. ``apply_scenarios`` keys its deltas by exact date, so an event
    dated before the forecast begins moves nothing at all — and the forecast
    begins the day after the last transaction, which on an account used today
    is tomorrow. Without the clamp, the panel's own default date ("today")
    would silently do nothing on exactly the accounts people use.

    Events past *horizon_end* are not emitted — they would be dropped by
    ``apply_scenarios`` anyway, and generating them first only costs time.
    """
    start = max(delta.start_date, horizon_start)

    if delta.kind is ScenarioDeltaKind.ONE_OFF:
        if start > horizon_end or delta.amount is None:
            return []
        return [ScenarioShift(label=delta.label, date=start, amount=float(delta.amount))]

    if delta.kind is ScenarioDeltaKind.INCOME_CHANGE:
        # An income change is a monthly rate change, so it compiles the same
        # way a monthly recurring delta does — once the percentage has been
        # read against real income.
        per_occurrence = monthly_amount(delta, monthly_income)
        cadence = RecurrenceFrequency.MONTHLY
    else:
        per_occurrence = delta.amount or Decimal("0")
        cadence = delta.cadence or RecurrenceFrequency.MONTHLY

    if per_occurrence == 0:
        return []

    amount = float(per_occurrence.quantize(_CENTS, rounding=ROUND_HALF_UP))
    shifts: list[ScenarioShift] = []
    day: datetime.date | None = start
    while day is not None and day <= horizon_end and len(shifts) < _MAX_OCCURRENCES:
        shifts.append(ScenarioShift(label=delta.label, date=day, amount=amount))
        day = _step(day, cadence)
    return shifts


def compile_deltas(
    deltas: list[ScenarioDelta],
    *,
    monthly_income: Decimal,
    horizon_start: datetime.date,
    horizon_end: datetime.date,
) -> list[ScenarioShift]:
    """Every delta's events, flattened. See :func:`compile_delta`."""
    return [
        shift
        for delta in deltas
        for shift in compile_delta(
            delta,
            monthly_income=monthly_income,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
        )
    ]


def monthly_cashflow_delta(deltas: list[ScenarioDelta], *, monthly_income: Decimal) -> Decimal:
    """What the scenario does to an average month, signed like the ledger.

    A one-off is not part of a monthly rate — it is a single event, and
    spreading it over the horizon would make a car purchase look like a
    subscription.
    """
    total = Decimal("0")
    for delta in deltas:
        if delta.kind is ScenarioDeltaKind.ONE_OFF:
            continue
        if delta.kind is ScenarioDeltaKind.INCOME_CHANGE:
            total += monthly_amount(delta, monthly_income)
        elif delta.cadence is not None and delta.amount is not None:
            total += delta.amount * occurrences_per_month(delta.cadence)
    return total.quantize(_CENTS, rounding=ROUND_HALF_UP)


def first_negative_date(result: ForecastResult) -> datetime.date | None:
    """The first forecast day the balance is below zero, if it ever is."""
    return next((p.date for p in result.forecast if p.value < 0), None)


def _ending_balance(result: ForecastResult) -> Decimal | None:
    forecast = result.forecast
    if not forecast:
        return None
    return Decimal(str(forecast[-1].value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class ScenarioSimulation:
    """A baseline, the same forecast with the deltas on it, and the verdict."""

    baseline: ForecastResult
    projected: ForecastResult
    verdict: ScenarioVerdict
    shifts: list[ScenarioShift]
    #: The first event of each delta, in the order the deltas were added —
    #: what the chart pins. Built per delta rather than deduped out of
    #: ``shifts``: two deltas can carry the same label (the dialog falls back
    #: to a default one when the name is left blank), and one recurring delta
    #: would otherwise use up a budget a later purchase needs.
    pins: list[ScenarioShift]


class ScenarioService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def trailing_monthly_income(
        self,
        *,
        account_id: int | None = None,
        today: datetime.date | None = None,
    ) -> Decimal:
        """Average monthly income over the same window the runway uses.

        Mirrors ``ReserveFundService.trailing_monthly_expense`` deliberately:
        a percentage income change read against a different window than the
        burn it is compared with would make the two figures incomparable.

        *account_id* scopes it to the account the baseline was drawn for.
        "Income −30%" on the salary account means 30% of what *that* account
        receives; measuring it against the household total would apply a cut
        the account never took.
        """
        ref = today or datetime.date.today()
        start = ref - datetime.timedelta(days=TRAILING_WINDOW_DAYS)
        stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.type == TransactionType.INCOME,
            Transaction.is_internal_transfer == False,  # noqa: E712
            Transaction.date >= start,
            Transaction.date <= ref,
        )
        if account_id is not None:
            stmt = stmt.where(Transaction.account_id == account_id)
        result = await self.session.execute(stmt)
        total = result.scalar_one() or Decimal("0")
        return Decimal(total) / TRAILING_WINDOW_MONTHS

    async def simulate(
        self,
        baseline: ForecastResult,
        deltas: list[ScenarioDelta],
        *,
        account_id: int | None = None,
        today: datetime.date | None = None,
    ) -> ScenarioSimulation:
        """Lay *deltas* over *baseline* and report what changed.

        *account_id* is the account *baseline* was drawn for, and scopes the
        income a percentage change is read against. The runway is deliberately
        not scoped: the Safety Funds panel measures it across the household,
        and one runway is the point.
        """
        ref = today or datetime.date.today()
        horizon_start = baseline.forecast[0].date if baseline.forecast else ref
        horizon_end = baseline.forecast[-1].date if baseline.forecast else ref

        monthly_income = await self.trailing_monthly_income(account_id=account_id, today=ref)
        per_delta = [
            compile_delta(
                delta,
                monthly_income=monthly_income,
                horizon_start=horizon_start,
                horizon_end=horizon_end,
            )
            for delta in deltas
        ]
        shifts = [shift for group in per_delta for shift in group]
        pins = [group[0] for group in per_delta if group]
        projected = apply_scenarios(baseline, shifts)

        funds = ReserveFundService(self.session)
        # The balances, not the panel's cover figure. That figure sums each
        # fund's months *after* rounding each to a tenth, so with two funds at
        # 1.04 months it reads 2.0 while one division of the total reads 2.1 —
        # and "before" and "after" would then differ with no delta at all.
        # Both ends of the pair go through `_runway`, so they are comparable;
        # the panel's own headline stays the panel's to define.
        emergency = await funds.emergency_progress(today=ref)
        fund_balance = sum((f.current_balance for f in emergency), Decimal("0"))
        burn = await funds.trailing_monthly_expense(today=ref)
        # No emergency fund at all means there is no answer to give, which is
        # not the same as a fund holding nothing.
        runway_before = self._runway(fund_balance, burn) if emergency else None

        verdict = ScenarioVerdict(
            monthly_delta=monthly_cashflow_delta(deltas, monthly_income=monthly_income),
            balance_before=_ending_balance(baseline),
            balance_after=_ending_balance(projected),
            first_negative_before=first_negative_date(baseline),
            first_negative_after=first_negative_date(projected),
            runway_before=runway_before,
            runway_after=(
                None
                if runway_before is None
                else self._runway_after(deltas, balance=fund_balance, burn=burn)
            ),
        )
        return ScenarioSimulation(
            baseline=baseline, projected=projected, verdict=verdict, shifts=shifts, pins=pins
        )

    @staticmethod
    def _runway_after(
        deltas: list[ScenarioDelta],
        *,
        balance: Decimal,
        burn: Decimal,
    ) -> Decimal | None:
        """Months of essentials the emergency funds still cover.

        Same definition as the Safety Funds panel — ``balance ÷ monthly
        essential spend`` — so the app has one runway, not two.

        **A scenario can only shorten it.** The figure answers "if income
        stopped, how long would the fund last", so nothing a scenario adds to
        income can lengthen it: not an income change, not a new recurring
        income stream, not a windfall. Income has already stopped inside the
        question. Those all move the projected balance instead, which is where
        a reader sees them.

        What does move it is spending: a purchase draws the fund down, because
        nothing records which pot it comes out of and treating a 40k car as
        free of the reserves would flatter the answer; and a new bill raises
        the burn the fund is divided by.
        """
        if burn <= 0:
            return None

        spent = sum(
            (
                -d.amount
                for d in deltas
                if d.kind is ScenarioDeltaKind.ONE_OFF and d.amount is not None and d.amount < 0
            ),
            Decimal("0"),
        )
        extra_burn = sum(
            (
                -d.amount * occurrences_per_month(d.cadence)
                for d in deltas
                if d.kind is ScenarioDeltaKind.RECURRING
                and d.cadence is not None
                and d.amount is not None
                and d.amount < 0
            ),
            Decimal("0"),
        )

        return ScenarioService._runway(balance - spent, burn + extra_burn)

    @staticmethod
    def _runway(balance: Decimal, burn: Decimal) -> Decimal | None:
        """``balance ÷ burn``, in months. ``None`` when nothing was spent.

        Both ends of the before/after pair go through here, so the pair is
        always comparable: a scenario that changes neither figure's inputs
        cannot make them differ.
        """
        if burn <= 0:
            return None
        return (max(balance, Decimal("0")) / burn).quantize(_TENTHS, rounding=ROUND_HALF_UP)


__all__ = [
    "DEFAULT_HORIZON_MONTHS",
    "MAX_HORIZON_MONTHS",
    "ScenarioService",
    "ScenarioSimulation",
    "compile_delta",
    "compile_deltas",
    "first_negative_date",
    "horizon_days",
    "monthly_amount",
    "monthly_cashflow_delta",
]
