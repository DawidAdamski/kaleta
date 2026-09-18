# SPDX-License-Identifier: AGPL-3.0-or-later
"""What-if deltas compiled onto a baseline forecast.

The simulator is post-processing, not a forecaster: every expectation here is
a literal read off a hand-built baseline, so a change in the forecasting
engine cannot quietly move these numbers.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

import pytest

from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.schemas.scenario import (
    ScenarioDelta,
    ScenarioDeltaKind,
    ScenarioVerdict,
    occurrences_per_month,
)
from kaleta.services.forecast_service import ForecastPoint, ForecastResult, apply_scenarios
from kaleta.services.scenario_service import (
    ScenarioService,
    compile_deltas,
    first_negative_date,
    monthly_cashflow_delta,
)

TODAY = datetime.date(2026, 1, 1)
HORIZON_END = datetime.date(2026, 12, 31)


def _baseline(*, start: float = 1000.0, drift: float = 0.0, days: int = 365) -> ForecastResult:
    """A flat (or steadily drifting) balance line, one point per day."""
    points = [
        ForecastPoint(
            date=TODAY - datetime.timedelta(days=1),
            value=start,
            lower=start,
            upper=start,
            is_forecast=False,
        )
    ]
    for offset in range(days):
        value = start + drift * (offset + 1)
        points.append(
            ForecastPoint(
                date=TODAY + datetime.timedelta(days=offset),
                value=value,
                lower=value - 50,
                upper=value + 50,
                is_forecast=True,
            )
        )
    return ForecastResult(account_name="Test", points=points)


def _one_off(amount: str, day: datetime.date, label: str = "Car") -> ScenarioDelta:
    return ScenarioDelta(
        kind=ScenarioDeltaKind.ONE_OFF, label=label, start_date=day, amount=Decimal(amount)
    )


def _recurring(
    amount: str,
    day: datetime.date,
    cadence: RecurrenceFrequency = RecurrenceFrequency.MONTHLY,
    label: str = "Gym",
) -> ScenarioDelta:
    return ScenarioDelta(
        kind=ScenarioDeltaKind.RECURRING,
        label=label,
        start_date=day,
        amount=Decimal(amount),
        cadence=cadence,
    )


class TestDeltaValidation:
    def test_an_income_change_needs_exactly_one_of_amount_or_percent(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            ScenarioDelta(kind=ScenarioDeltaKind.INCOME_CHANGE, label="Raise", start_date=TODAY)
        with pytest.raises(ValueError, match="exactly one"):
            ScenarioDelta(
                kind=ScenarioDeltaKind.INCOME_CHANGE,
                label="Raise",
                start_date=TODAY,
                amount=Decimal("100"),
                percent=Decimal("10"),
            )

    def test_a_recurring_delta_needs_a_cadence(self) -> None:
        with pytest.raises(ValueError, match="cadence"):
            ScenarioDelta(
                kind=ScenarioDeltaKind.RECURRING,
                label="Gym",
                start_date=TODAY,
                amount=Decimal("-100"),
            )

    def test_a_one_off_needs_an_amount(self) -> None:
        with pytest.raises(ValueError, match="needs an amount"):
            ScenarioDelta(kind=ScenarioDeltaKind.ONE_OFF, label="Car", start_date=TODAY)

    def test_income_cannot_fall_by_more_than_everything(self) -> None:
        with pytest.raises(ValueError, match="more than 100"):
            ScenarioDelta(
                kind=ScenarioDeltaKind.INCOME_CHANGE,
                label="Ruin",
                start_date=TODAY,
                percent=Decimal("-120"),
            )


class TestCompileDeltas:
    def test_a_one_off_is_a_single_event_on_its_day(self) -> None:
        shifts = compile_deltas(
            [_one_off("-40000", datetime.date(2026, 3, 15))],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert len(shifts) == 1
        assert shifts[0].date == datetime.date(2026, 3, 15)
        assert shifts[0].amount == -40000.0

    def test_a_one_off_before_the_forecast_starts_lands_on_its_first_point(self) -> None:
        """The panel offers "today"; on an account used today, the forecast
        starts tomorrow. ``apply_scenarios`` keys on the exact date, so
        without the clamp the delta would move nothing at all.
        """
        starts = datetime.date(2026, 1, 5)
        shifts = compile_deltas(
            [_one_off("-40000", datetime.date(2026, 1, 1))],
            monthly_income=Decimal("5000"),
            horizon_start=starts,
            horizon_end=HORIZON_END,
        )
        assert [(s.date, s.amount) for s in shifts] == [(starts, -40000.0)]

    def test_a_recurring_delta_steps_from_the_first_forecast_point(self) -> None:
        """Snapped forward, then stepped — not all stacked on day one."""
        starts = datetime.date(2026, 1, 5)
        shifts = compile_deltas(
            [_recurring("-300", datetime.date(2025, 11, 20))],
            monthly_income=Decimal("5000"),
            horizon_start=starts,
            horizon_end=datetime.date(2026, 4, 30),
        )
        assert [s.date for s in shifts] == [
            datetime.date(2026, 1, 5),
            datetime.date(2026, 2, 5),
            datetime.date(2026, 3, 5),
            datetime.date(2026, 4, 5),
        ]

    def test_a_one_off_past_the_horizon_is_not_emitted(self) -> None:
        shifts = compile_deltas(
            [_one_off("-40000", datetime.date(2027, 3, 15))],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert shifts == []

    def test_a_monthly_bill_becomes_one_event_per_month(self) -> None:
        """A bill is withdrawals on the days they happen, not an averaged slope."""
        shifts = compile_deltas(
            [_recurring("-300", datetime.date(2026, 1, 10))],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert len(shifts) == 12
        assert [s.date.month for s in shifts] == list(range(1, 13))
        assert all(s.amount == -300.0 for s in shifts)

    def test_a_monthly_cadence_clamps_to_the_end_of_a_short_month(self) -> None:
        """The 31st has no February, and must not roll into March."""
        shifts = compile_deltas(
            [_recurring("-100", datetime.date(2026, 1, 31))],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=datetime.date(2026, 4, 30),
        )
        assert [s.date for s in shifts] == [
            datetime.date(2026, 1, 31),
            datetime.date(2026, 2, 28),
            datetime.date(2026, 3, 28),
            datetime.date(2026, 4, 28),
        ]

    def test_a_yearly_cadence_fires_once_inside_a_one_year_horizon(self) -> None:
        shifts = compile_deltas(
            [_recurring("-1200", datetime.date(2026, 6, 1), RecurrenceFrequency.YEARLY)],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert len(shifts) == 1

    def test_a_percentage_income_cut_is_read_against_real_income(self) -> None:
        """The balance series never says what came in — only what was left."""
        shifts = compile_deltas(
            [
                ScenarioDelta(
                    kind=ScenarioDeltaKind.INCOME_CHANGE,
                    label="−30%",
                    start_date=datetime.date(2026, 2, 1),
                    percent=Decimal("-30"),
                )
            ],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert len(shifts) == 11
        assert all(s.amount == -1500.0 for s in shifts)

    def test_an_absolute_income_change_needs_no_income_to_read(self) -> None:
        shifts = compile_deltas(
            [
                ScenarioDelta(
                    kind=ScenarioDeltaKind.INCOME_CHANGE,
                    label="Raise",
                    start_date=datetime.date(2026, 1, 1),
                    amount=Decimal("450"),
                )
            ],
            monthly_income=Decimal("0"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert all(s.amount == 450.0 for s in shifts)

    def test_a_zero_delta_emits_nothing(self) -> None:
        shifts = compile_deltas(
            [_recurring("0", TODAY)],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        assert shifts == []

    def test_no_deltas_compile_to_no_shifts(self) -> None:
        assert (
            compile_deltas(
                [], monthly_income=Decimal("5000"), horizon_start=TODAY, horizon_end=HORIZON_END
            )
            == []
        )


class TestProjection:
    def test_removing_every_delta_restores_the_baseline_exactly(self) -> None:
        """The panel promises the overlay is reversible, to the cent."""
        baseline = _baseline()
        projected = apply_scenarios(
            baseline,
            compile_deltas(
                [_one_off("-40000", datetime.date(2026, 3, 15))],
                monthly_income=Decimal("5000"),
                horizon_start=TODAY,
                horizon_end=HORIZON_END,
            ),
        )
        restored = apply_scenarios(baseline, [])

        assert [p.value for p in projected.forecast] != [p.value for p in baseline.forecast]
        assert [p.value for p in restored.forecast] == [p.value for p in baseline.forecast]

    def test_a_purchase_steps_the_line_down_on_its_day_and_stays_down(self) -> None:
        baseline = _baseline(start=50000.0)
        shifts = compile_deltas(
            [_one_off("-40000", datetime.date(2026, 3, 15))],
            monthly_income=Decimal("5000"),
            horizon_start=TODAY,
            horizon_end=HORIZON_END,
        )
        projected = apply_scenarios(baseline, shifts)
        by_date = {p.date: p.value for p in projected.forecast}

        assert by_date[datetime.date(2026, 3, 14)] == 50000.0
        assert by_date[datetime.date(2026, 3, 15)] == 10000.0
        assert by_date[datetime.date(2026, 12, 31)] == 10000.0

    def test_the_confidence_band_moves_with_the_line(self) -> None:
        """A band left behind would sit around a prediction no longer made."""
        baseline = _baseline()
        projected = apply_scenarios(
            baseline,
            compile_deltas(
                [_one_off("-500", datetime.date(2026, 2, 1))],
                monthly_income=Decimal("5000"),
                horizon_start=TODAY,
                horizon_end=HORIZON_END,
            ),
        )
        point = next(p for p in projected.forecast if p.date == datetime.date(2026, 2, 1))
        assert point.value == 500.0
        assert point.lower == 450.0
        assert point.upper == 550.0

    def test_history_is_never_touched(self) -> None:
        baseline = _baseline()
        projected = apply_scenarios(
            baseline,
            compile_deltas(
                [_one_off("-40000", datetime.date(2026, 3, 15))],
                monthly_income=Decimal("5000"),
                horizon_start=TODAY,
                horizon_end=HORIZON_END,
            ),
        )
        assert [p.value for p in projected.historical] == [p.value for p in baseline.historical]


class TestFirstNegative:
    def test_a_baseline_that_stays_positive_has_no_first_negative_day(self) -> None:
        assert first_negative_date(_baseline()) is None

    def test_the_purchase_that_empties_the_account_is_dated(self) -> None:
        projected = apply_scenarios(
            _baseline(start=1000.0),
            compile_deltas(
                [_one_off("-4000", datetime.date(2026, 5, 20))],
                monthly_income=Decimal("5000"),
                horizon_start=TODAY,
                horizon_end=HORIZON_END,
            ),
        )
        assert first_negative_date(projected) == datetime.date(2026, 5, 20)

    def test_a_new_bill_moves_the_marker_earlier(self) -> None:
        """KAL-WIF-003's shape: the same account runs out sooner."""
        # −4/day from 1000 crosses zero partway through the year, so there
        # is a baseline marker for the bill to move.
        baseline = _baseline(start=1000.0, drift=-4.0)
        before = first_negative_date(baseline)
        after = first_negative_date(
            apply_scenarios(
                baseline,
                compile_deltas(
                    [_recurring("-200", datetime.date(2026, 1, 5))],
                    monthly_income=Decimal("5000"),
                    horizon_start=TODAY,
                    horizon_end=HORIZON_END,
                ),
            )
        )
        assert before is not None
        assert after is not None
        assert after < before


class TestMonthlyCashflowDelta:
    def test_a_one_off_is_not_part_of_a_monthly_rate(self) -> None:
        """Spreading a car over the horizon would read as a subscription."""
        delta = monthly_cashflow_delta(
            [_one_off("-40000", datetime.date(2026, 3, 15))], monthly_income=Decimal("5000")
        )
        assert delta == Decimal("0.00")

    def test_a_monthly_bill_is_its_own_amount(self) -> None:
        delta = monthly_cashflow_delta([_recurring("-300", TODAY)], monthly_income=Decimal("5000"))
        assert delta == Decimal("-300.00")

    def test_a_yearly_bill_is_a_twelfth_of_itself(self) -> None:
        delta = monthly_cashflow_delta(
            [_recurring("-1200", TODAY, RecurrenceFrequency.YEARLY)],
            monthly_income=Decimal("5000"),
        )
        assert delta == Decimal("-100.00")

    def test_a_percentage_cut_is_the_share_of_real_income(self) -> None:
        delta = monthly_cashflow_delta(
            [
                ScenarioDelta(
                    kind=ScenarioDeltaKind.INCOME_CHANGE,
                    label="−30%",
                    start_date=TODAY,
                    percent=Decimal("-30"),
                )
            ],
            monthly_income=Decimal("5000"),
        )
        assert delta == Decimal("-1500.00")

    def test_deltas_add_up(self) -> None:
        delta = monthly_cashflow_delta(
            [_recurring("-300", TODAY), _recurring("-1200", TODAY, RecurrenceFrequency.YEARLY)],
            monthly_income=Decimal("5000"),
        )
        assert delta == Decimal("-400.00")

    @pytest.mark.parametrize(
        ("cadence", "expected"),
        [
            (RecurrenceFrequency.MONTHLY, Decimal("1")),
            (RecurrenceFrequency.QUARTERLY, Decimal("1") / Decimal("3")),
            (RecurrenceFrequency.YEARLY, Decimal("1") / Decimal("12")),
            (RecurrenceFrequency.ONCE, Decimal("0")),
        ],
    )
    def test_cadence_to_monthly_rate(self, cadence: RecurrenceFrequency, expected: Decimal) -> None:
        assert occurrences_per_month(cadence) == expected


class TestRunway:
    """The Safety Funds definition, borrowed whole: balance / monthly burn."""

    @staticmethod
    def _after(deltas: list[ScenarioDelta], *, runway: str = "6.0", burn: str = "2000") -> Decimal:
        value = ScenarioService._runway_after(
            deltas,
            runway_before=Decimal(runway),
            burn=Decimal(burn),
            monthly_income=Decimal("5000"),
        )
        assert value is not None
        return value

    def test_no_deltas_leave_the_runway_where_it_was(self) -> None:
        assert self._after([]) == Decimal("6.0")

    def test_a_purchase_draws_the_fund_down(self) -> None:
        """12000 set aside, 4000 spent, 2000 a month → four months left."""
        assert self._after([_one_off("-4000", TODAY)]) == Decimal("4.0")

    def test_a_new_bill_raises_the_burn(self) -> None:
        """12000 against 2500 a month is 4.8 months."""
        assert self._after([_recurring("-500", TODAY)]) == Decimal("4.8")

    def test_an_income_change_does_not_move_the_runway(self) -> None:
        """The figure already assumes income stopped — see the docstring."""
        cut = ScenarioDelta(
            kind=ScenarioDeltaKind.INCOME_CHANGE,
            label="−30%",
            start_date=TODAY,
            percent=Decimal("-30"),
        )
        assert self._after([cut]) == Decimal("6.0")

    def test_a_purchase_bigger_than_the_fund_empties_it_rather_than_going_negative(self) -> None:
        assert self._after([_one_off("-99000", TODAY)]) == Decimal("0.0")

    def test_no_emergency_fund_means_no_runway_to_report(self) -> None:
        assert (
            ScenarioService._runway_after(
                [], runway_before=None, burn=Decimal("2000"), monthly_income=Decimal("5000")
            )
            is None
        )

    def test_nothing_spent_means_no_runway_to_report(self) -> None:
        """Dividing by a zero burn would claim infinite cover."""
        assert (
            ScenarioService._runway_after(
                [], runway_before=Decimal("6"), burn=Decimal("0"), monthly_income=Decimal("5000")
            )
            is None
        )


class TestVerdict:
    def test_goes_negative_only_when_the_baseline_did_not(self) -> None:
        def verdict(before: datetime.date | None, after: datetime.date | None) -> ScenarioVerdict:
            return ScenarioVerdict(
                monthly_delta=Decimal("0"),
                balance_before=None,
                balance_after=None,
                first_negative_before=before,
                first_negative_after=after,
                runway_before=None,
                runway_after=None,
            )

        assert verdict(None, datetime.date(2026, 5, 1)).goes_negative is True
        assert verdict(datetime.date(2026, 4, 1), datetime.date(2026, 5, 1)).goes_negative is False
        assert verdict(None, None).goes_negative is False


class TestTrailingIncome:
    """The figure a percentage income change is read against."""

    @staticmethod
    async def _seed(session: object, *, account_id: int, amount: str, day: datetime.date) -> None:
        from kaleta.models.account import Account
        from kaleta.models.transaction import Transaction, TransactionType

        s: Any = session
        if await s.get(Account, account_id) is None:
            s.add(Account(id=account_id, name=f"Account {account_id}", balance=Decimal("0")))
            await s.flush()
        s.add(
            Transaction(
                account_id=account_id,
                amount=Decimal(amount),
                type=TransactionType.INCOME,
                date=day,
                description="salary",
            )
        )
        await s.flush()

    @pytest.mark.asyncio
    async def test_the_window_is_ninety_days_over_three(self, session: Any) -> None:
        """Three months of 3000 reads as 3000 a month, not 9000."""
        for month in (0, 1, 2):
            await self._seed(
                session,
                account_id=1,
                amount="3000",
                day=TODAY - datetime.timedelta(days=30 * month),
            )

        income = await ScenarioService(session).trailing_monthly_income(today=TODAY)

        assert income == Decimal("3000")

    @pytest.mark.asyncio
    async def test_income_outside_the_window_does_not_count(self, session: Any) -> None:
        await self._seed(session, account_id=1, amount="9000", day=TODAY - datetime.timedelta(91))

        income = await ScenarioService(session).trailing_monthly_income(today=TODAY)

        assert income == Decimal("0")

    @pytest.mark.asyncio
    async def test_an_account_is_read_against_its_own_income(self, session: Any) -> None:
        """ "Income -30%" on the salary account is 30% of what *it* receives.

        Covers the case the household total would get wrong: a second account
        earning nine times as much must not inflate the first one's cut.
        """
        await self._seed(session, account_id=1, amount="3000", day=TODAY)
        await self._seed(session, account_id=2, amount="27000", day=TODAY)

        svc = ScenarioService(session)

        assert await svc.trailing_monthly_income(account_id=1, today=TODAY) == Decimal("1000")
        assert await svc.trailing_monthly_income(account_id=2, today=TODAY) == Decimal("9000")
        assert await svc.trailing_monthly_income(today=TODAY) == Decimal("10000")
