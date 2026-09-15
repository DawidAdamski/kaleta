# SPDX-License-Identifier: AGPL-3.0-or-later
"""What one day cell of the Payment Calendar draws (artboard 3c).

The cell used to stack an inflow line, an outflow line and a count badge —
three numbers, thirty-one times over. ``day_marks`` reduces a day to the one
figure that says which way it goes and one dot per thing happening, which is
what the counts were for. Presentational; no BDD scenario claims it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.schemas.wizard_projections import SubscriptionCharge
from kaleta.services.planned_transaction_service import DayAggregate, PlannedOccurrence
from kaleta.views.payment_calendar import DOT_CAP, day_marks
from kaleta.views.theme import CALENDAR_DOT_FLAT, CALENDAR_DOT_IN, CALENDAR_DOT_OUT

DAY = datetime.date(2025, 3, 14)


def _occ(amount: str, kind: TransactionType) -> PlannedOccurrence:
    return PlannedOccurrence(
        date=DAY,
        planned_id=1,
        name="Item",
        amount=Decimal(amount),
        type=kind,
        account_id=1,
        account_name="PKO",
        category_id=None,
        category_name=None,
    )


def _cell(*occurrences: PlannedOccurrence) -> DayAggregate:
    inflow = sum(
        (abs(o.amount) for o in occurrences if o.type == TransactionType.INCOME), Decimal("0")
    )
    outflow = sum(
        (abs(o.amount) for o in occurrences if o.type == TransactionType.EXPENSE), Decimal("0")
    )
    return DayAggregate(date=DAY, inflow=inflow, outflow=outflow, occurrences=list(occurrences))


def _sub(amount: str) -> SubscriptionCharge:
    return SubscriptionCharge(subscription_id=1, date=DAY, name="Netflix", amount=Decimal(amount))


class TestDayMarks:
    def test_a_day_with_nothing_on_it_has_no_figure_and_no_dots(self) -> None:
        marks = day_marks(None, [])
        assert marks.net == Decimal("0")
        assert marks.is_empty
        assert marks.overflow == 0

    def test_one_dot_per_thing_happening_coloured_by_direction(self) -> None:
        cell = _cell(
            _occ("100.00", TransactionType.INCOME),
            _occ("40.00", TransactionType.EXPENSE),
        )
        assert day_marks(cell, []).dots == (CALENDAR_DOT_IN, CALENDAR_DOT_OUT)

    def test_the_figure_is_the_day_net_not_two_totals(self) -> None:
        cell = _cell(
            _occ("100.00", TransactionType.INCOME),
            _occ("40.00", TransactionType.EXPENSE),
        )
        assert day_marks(cell, []).net == Decimal("60.00")

    def test_a_transfer_is_drawn_flat(self) -> None:
        # The service counts a transfer in neither inflow nor outflow, so a
        # coloured dot would give the day a direction its own net has not got.
        cell = _cell(_occ("500.00", TransactionType.TRANSFER))
        marks = day_marks(cell, [])
        assert marks.dots == (CALENDAR_DOT_FLAT,)
        assert marks.net == Decimal("0")

    def test_a_projected_subscription_is_flat_but_still_counts_against_the_day(self) -> None:
        # It is the one item in the cell the user cannot post, so it does not
        # take the expense colour — but it is money leaving all the same.
        marks = day_marks(None, [_sub("29.99")])
        assert marks.dots == (CALENDAR_DOT_FLAT,)
        assert marks.net == Decimal("-29.99")

    def test_subscriptions_come_after_the_planned_items(self) -> None:
        cell = _cell(_occ("10.00", TransactionType.INCOME))
        assert day_marks(cell, [_sub("5.00")]).dots == (CALENDAR_DOT_IN, CALENDAR_DOT_FLAT)

    def test_a_busy_day_caps_its_dots_and_counts_the_rest(self) -> None:
        cell = _cell(*(_occ("1.00", TransactionType.EXPENSE) for _ in range(DOT_CAP + 3)))
        marks = day_marks(cell, [])
        assert len(marks.dots) == DOT_CAP
        assert marks.overflow == 3

    def test_a_day_exactly_at_the_cap_has_no_tail(self) -> None:
        cell = _cell(*(_occ("1.00", TransactionType.EXPENSE) for _ in range(DOT_CAP)))
        marks = day_marks(cell, [])
        assert len(marks.dots) == DOT_CAP
        assert marks.overflow == 0

    def test_the_cap_counts_subscriptions_too(self) -> None:
        cell = _cell(*(_occ("1.00", TransactionType.EXPENSE) for _ in range(DOT_CAP)))
        assert day_marks(cell, [_sub("5.00")]).overflow == 1

    def test_a_day_that_nets_to_zero_still_shows_its_dots(self) -> None:
        # Two items that cancel out is not the same as an empty day, and the
        # cell hides the figure when it is zero — the dots are what is left.
        cell = _cell(
            _occ("50.00", TransactionType.INCOME),
            _occ("50.00", TransactionType.EXPENSE),
        )
        marks = day_marks(cell, [])
        assert marks.net == Decimal("0")
        assert not marks.is_empty
