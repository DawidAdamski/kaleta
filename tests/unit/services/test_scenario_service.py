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
    compile_delta,
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

    def test_a_percentage_belongs_to_an_income_change_alone(self) -> None:
        """Ignoring it would apply half the delta and say nothing about the rest."""
        for kind in (ScenarioDeltaKind.ONE_OFF, ScenarioDeltaKind.RECURRING):
            with pytest.raises(ValueError, match="not a percentage"):
                ScenarioDelta(
                    kind=kind,
                    label="Car",
                    start_date=TODAY,
                    amount=Decimal("-40000"),
                    percent=Decimal("-30"),
                    cadence=RecurrenceFrequency.MONTHLY,
                )

    def test_only_a_recurring_delta_carries_a_cadence(self) -> None:
        for kind in (ScenarioDeltaKind.ONE_OFF, ScenarioDeltaKind.INCOME_CHANGE):
            with pytest.raises(ValueError, match="no cadence"):
                ScenarioDelta(
                    kind=kind,
                    label="Car",
                    start_date=TODAY,
                    amount=Decimal("-40000"),
                    cadence=RecurrenceFrequency.MONTHLY,
                )

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
    """The Safety Funds definition, borrowed whole: balance / monthly burn.

    12,000 set aside against 2,000 a month is six months, which is what every
    case below starts from.
    """

    @staticmethod
    def _after(
        deltas: list[ScenarioDelta], *, balance: str = "12000", burn: str = "2000"
    ) -> Decimal:
        value = ScenarioService._runway_after(deltas, balance=Decimal(balance), burn=Decimal(burn))
        assert value is not None
        return value

    @staticmethod
    def _income(percent: str = "-30") -> ScenarioDelta:
        return ScenarioDelta(
            kind=ScenarioDeltaKind.INCOME_CHANGE,
            label=f"{percent}%",
            start_date=TODAY,
            percent=Decimal(percent),
        )

    def test_no_deltas_leave_the_runway_where_it_was(self) -> None:
        assert self._after([]) == Decimal("6.0")

    def test_a_purchase_draws_the_fund_down(self) -> None:
        """12000 set aside, 4000 spent, 2000 a month → four months left."""
        assert self._after([_one_off("-4000", TODAY)]) == Decimal("4.0")

    def test_a_new_bill_raises_the_burn(self) -> None:
        """12000 against 2500 a month is 4.8 months."""
        assert self._after([_recurring("-500", TODAY)]) == Decimal("4.8")

    # ── The runway is a floor: a scenario can only shorten it ──────────────

    def test_an_income_cut_does_not_move_the_runway(self) -> None:
        """The figure already assumes income stopped — see the docstring."""
        assert self._after([self._income("-30")]) == Decimal("6.0")

    def test_a_raise_does_not_lengthen_the_runway(self) -> None:
        assert self._after([self._income("+50")]) == Decimal("6.0")

    def test_a_new_income_stream_does_not_lengthen_the_runway(self) -> None:
        """Money that arrives monthly is income, and income has stopped.

        It would otherwise lower the burn and stretch the runway, while an
        income change of the same size left it alone — two answers to the
        same question.
        """
        assert self._after([_recurring("+500", TODAY, label="Lodger")]) == Decimal("6.0")

    def test_a_windfall_does_not_top_the_fund_up(self) -> None:
        """Nothing says a windfall lands in the emergency fund."""
        assert self._after([_one_off("+4000", TODAY, label="Bonus")]) == Decimal("6.0")

    def test_spending_still_counts_when_a_windfall_is_beside_it(self) -> None:
        assert self._after(
            [_one_off("+4000", TODAY, label="Bonus"), _one_off("-4000", TODAY)]
        ) == Decimal("4.0")

    # ── Edges ─────────────────────────────────────────────────────────────

    def test_a_purchase_bigger_than_the_fund_empties_it_rather_than_going_negative(self) -> None:
        assert self._after([_one_off("-99000", TODAY)]) == Decimal("0.0")

    def test_nothing_spent_means_no_runway_to_report(self) -> None:
        """Dividing by a zero burn would claim infinite cover."""
        assert (
            ScenarioService._runway_after([], balance=Decimal("12000"), burn=Decimal("0")) is None
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


class TestSimulate:
    """The whole pass, end to end, against a real session."""

    @staticmethod
    async def _seed_emergency_fund(session: Any, *, name: str, balance: str) -> None:
        """One emergency fund, backed by an account holding *balance*."""
        from kaleta.models.account import Account
        from kaleta.models.reserve_fund import (
            ReserveFund,
            ReserveFundBackingMode,
            ReserveFundKind,
        )

        s: Any = session
        account = Account(name=f"{name} backing", balance=Decimal(balance))
        s.add(account)
        await s.flush()
        s.add(
            ReserveFund(
                name=name,
                kind=ReserveFundKind.EMERGENCY,
                target_amount=Decimal("100000"),
                backing_mode=ReserveFundBackingMode.ACCOUNT,
                backing_account_id=account.id,
                emergency_multiplier=3,
            )
        )
        await s.flush()

    @staticmethod
    async def _seed_expense(session: Any, amount: str) -> None:
        from kaleta.models.account import Account
        from kaleta.models.transaction import Transaction, TransactionType

        s: Any = session
        spender = Account(name="Spender", balance=Decimal("0"))
        s.add(spender)
        await s.flush()
        s.add(
            Transaction(
                account_id=spender.id,
                amount=Decimal(amount),
                type=TransactionType.EXPENSE,
                date=TODAY,
                description="rent",
            )
        )
        await s.flush()

    @pytest.mark.asyncio
    async def test_two_funds_and_no_deltas_leave_the_runway_untouched(self, session: Any) -> None:
        """The before/after pair has to be comparable, with any number of funds.

        The panel's own cover figure sums each fund's months *after* rounding
        each to a tenth, so two funds at 1.04 months read 2.0 there while one
        division of the total reads 2.1 — and the verdict would show a change
        no delta caused.
        """
        await self._seed_expense(session, "6000")  # 6000 over 90 days → 2000 a month
        await self._seed_emergency_fund(session, name="Fund A", balance="2080")
        await self._seed_emergency_fund(session, name="Fund B", balance="2080")

        verdict = (await ScenarioService(session).simulate(_baseline(), [], today=TODAY)).verdict

        assert verdict.runway_before == verdict.runway_after
        # 4160 / 2000 = 2.08 → 2.1, divided once rather than summed rounded.
        assert verdict.runway_before == Decimal("2.1")

    @pytest.mark.asyncio
    async def test_no_emergency_fund_means_no_runway_to_report(self, session: Any) -> None:
        """``None`` is "no answer to give", and a scenario cannot conjure one.

        The guard lives in ``simulate`` rather than in ``_runway_after``,
        which sees a balance of zero and would answer 0.0 months — a figure,
        where there is none.
        """
        simulation = await ScenarioService(session).simulate(
            _baseline(), [_one_off("-1000", TODAY)], today=TODAY
        )

        assert simulation.verdict.runway_before is None
        assert simulation.verdict.runway_after is None
        # The rest of the verdict still answers, which is the point of a floor
        # that is allowed to be missing.
        assert simulation.verdict.balance_after == Decimal("0.00")
        assert simulation.verdict.balance_before == Decimal("1000.00")


class TestChartPins:
    """``simulation.pins`` — the first event of each delta, in order."""

    @staticmethod
    def _pins(deltas: list[ScenarioDelta]) -> list[tuple[str, datetime.date]]:
        per_delta = [
            compile_delta(
                d,
                monthly_income=Decimal("5000"),
                horizon_start=TODAY,
                horizon_end=HORIZON_END,
            )
            for d in deltas
        ]
        return [(g[0].label, g[0].date) for g in per_delta if g]

    def test_one_pin_per_delta_in_the_order_they_were_added(self) -> None:
        """A recurring delta must not use up the budget a later one needs."""
        deltas = [
            _recurring("-300", TODAY, label="Gym"),
            _one_off("-40000", datetime.date(2026, 6, 1), label="Car"),
        ]
        assert (
            len(
                compile_deltas(
                    deltas,
                    monthly_income=Decimal("5000"),
                    horizon_start=TODAY,
                    horizon_end=HORIZON_END,
                )
            )
            == 13
        ), "twelve gym payments and one car"

        assert self._pins(deltas) == [
            ("Gym", TODAY),
            ("Car", datetime.date(2026, 6, 1)),
        ]

    def test_two_deltas_sharing_a_label_still_get_a_pin_each(self) -> None:
        """The dialog falls back to the same default name when one is blank.

        Deduping by label would have collapsed these into one pin and left the
        second purchase unmarked.
        """
        deltas = [
            _one_off("-1000", datetime.date(2026, 2, 1), label="One-off amount"),
            _one_off("-2000", datetime.date(2026, 8, 1), label="One-off amount"),
        ]

        assert self._pins(deltas) == [
            ("One-off amount", datetime.date(2026, 2, 1)),
            ("One-off amount", datetime.date(2026, 8, 1)),
        ]

    def test_a_delta_that_emits_nothing_gets_no_pin(self) -> None:
        assert self._pins([_one_off("-500", datetime.date(2030, 1, 1))]) == []
