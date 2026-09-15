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
from kaleta.views.payment_calendar import (
    DOT_CAP,
    actually_overdue,
    day_marks,
    occurrence_amount,
    overdue_age_label,
)
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    AMOUNT_NEUTRAL,
    CALENDAR_DOT_FLAT,
    CALENDAR_DOT_IN,
    CALENDAR_DOT_OUT,
)

DAY = datetime.date(2025, 3, 14)


def _occ(amount: str, kind: TransactionType, date: datetime.date = DAY) -> PlannedOccurrence:
    return PlannedOccurrence(
        date=date,
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


class TestActuallyOverdue:
    """Covers the strip's window (artboard 3c).

    ``grid_for_month`` windows its overdue bucket against the browsed month,
    not against today. The strip has to correct for that or it prints ages
    for occurrences that have not happened yet.
    """

    def test_an_occurrence_still_to_come_is_not_late(self) -> None:
        today = datetime.date(2025, 3, 14)
        future = _occ("10.00", TransactionType.EXPENSE, today + datetime.timedelta(days=5))
        assert actually_overdue([future], today) == []

    def test_todays_own_occurrence_is_not_late_yet(self) -> None:
        today = datetime.date(2025, 3, 14)
        assert actually_overdue([_occ("10.00", TransactionType.EXPENSE, today)], today) == []

    def test_yesterdays_is(self) -> None:
        today = datetime.date(2025, 3, 14)
        late = _occ("10.00", TransactionType.EXPENSE, today - datetime.timedelta(days=1))
        assert actually_overdue([late], today) == [late]

    def test_the_oldest_debt_is_listed_first(self) -> None:
        today = datetime.date(2025, 3, 14)
        recent = _occ("10.00", TransactionType.EXPENSE, today - datetime.timedelta(days=2))
        old = _occ("10.00", TransactionType.EXPENSE, today - datetime.timedelta(days=20))
        assert actually_overdue([recent, old], today) == [old, recent]


class TestOverdueAgeLabel:
    """How long a thing has been waiting, in a language with three plurals."""

    def test_one_day_is_singular(self) -> None:
        today = datetime.date(2025, 3, 14)
        assert overdue_age_label(today - datetime.timedelta(days=1), today) == "1 day late"

    def test_more_than_one_is_not(self) -> None:
        today = datetime.date(2025, 3, 14)
        assert overdue_age_label(today - datetime.timedelta(days=12), today) == "12 days late"

    def test_today_is_not_late_at_all(self) -> None:
        # The strip never shows it (see actually_overdue), but the label must
        # not read "-0 days" if something ever hands it one.
        today = datetime.date(2025, 3, 14)
        assert overdue_age_label(today, today) == "0 days late"

    def test_polish_has_a_form_for_each_count(self) -> None:
        # dzień / dni. `t()` takes the language from NiceGUI's per-user
        # storage, which a unit test has not got, so the locale file itself is
        # what is asserted: the key the helper asks for must exist and read
        # correctly for all three shapes.
        forms = _pl_forms()
        assert forms[1].format(days=1) == "1 dzień po terminie"
        assert forms[3].format(days=3) == "3 dni po terminie"
        assert forms[22].format(days=22) == "22 dni po terminie"


def _pl_forms() -> dict[int, str]:
    """The Polish string ``overdue_age_label`` would pick, per count."""
    import json
    from pathlib import Path

    import kaleta.i18n
    from kaleta.i18n import plural_key

    # Resolved from the package, not the working directory.
    path = Path(kaleta.i18n.__file__).parent / "locales" / "pl.json"
    locale = json.loads(path.read_text(encoding="utf-8"))["payment_calendar"]
    return {
        n: locale[plural_key("payment_calendar.overdue_age", n).rsplit(".", 1)[1]]
        for n in (1, 3, 22)
    }


class TestOccurrenceAmount:
    """One rule for the figure, read the same way in the strip and the sheet."""

    def test_income_is_signed_up(self) -> None:
        assert occurrence_amount(_occ("210.00", TransactionType.INCOME)) == (
            "+210.00",
            AMOUNT_INCOME,
        )

    def test_an_expense_is_signed_down(self) -> None:
        assert occurrence_amount(_occ("210.00", TransactionType.EXPENSE)) == (
            "-210.00",
            AMOUNT_EXPENSE,
        )

    def test_a_transfer_is_neither(self) -> None:
        # Money between the user's own accounts did not leave, so signing it
        # as an expense would say something that did not happen — and the
        # day cell's dot for the same item is already flat.
        assert occurrence_amount(_occ("500.00", TransactionType.TRANSFER)) == (
            "500.00",
            AMOUNT_NEUTRAL,
        )

    def test_a_negative_amount_is_read_by_its_kind_not_its_sign(self) -> None:
        assert occurrence_amount(_occ("-80.00", TransactionType.EXPENSE))[0] == "-80.00"
