# SPDX-License-Identifier: AGPL-3.0-or-later
"""What one day of the payment calendar comes to.

Three readers ask the same question of a day — the cell in the month grid,
the sheet's Out, the sheet's Net — and they used to answer it separately, in
the view, which is how a day drawn `-12.99` came to open onto `Out 0.00`.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from kaleta.schemas.transaction import TransactionType
from kaleta.schemas.wizard_projections import SubscriptionCharge
from kaleta.services.day_totals import DayTotals
from kaleta.services.planned_transaction_service import DayAggregate, PlannedOccurrence
from kaleta.views.payment_calendar import day_marks

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


class TestDayTotals:
    """The three figures the day sheet opens with.

    They are the same arithmetic the cell in the grid does, and the two used
    to disagree: a day drawn `-12.99` opened onto `Out 0.00` because only
    the cell counted the subscription charges.
    """

    def test_a_charge_leaves_on_the_day_it_is_charged(self) -> None:
        cell = _cell(_occ("35.00", TransactionType.EXPENSE))
        assert DayTotals.outgoing(cell, [_sub("12.99")]) == Decimal("47.99")
        assert DayTotals.net(cell, [_sub("12.99")]) == Decimal("-47.99")

    def test_a_charge_is_never_money_coming_in(self) -> None:
        cell = _cell(_occ("100.00", TransactionType.INCOME))
        assert DayTotals.incoming(cell) == Decimal("100.00")
        assert DayTotals.outgoing(cell, [_sub("12.99")]) == Decimal("12.99")

    def test_the_sheet_and_the_cell_agree(self) -> None:
        cell = _cell(_occ("100.00", TransactionType.INCOME), _occ("35.00", TransactionType.EXPENSE))
        subs = [_sub("12.99"), _sub("10.75")]
        assert DayTotals.net(cell, subs) == day_marks(cell, subs).net

    def test_a_day_with_nothing_on_it(self) -> None:
        assert DayTotals.incoming(None) == Decimal("0")
        assert DayTotals.outgoing(None) == Decimal("0")
        assert DayTotals.net(None) == Decimal("0")

    def test_charges_add_up(self) -> None:
        assert DayTotals.charged([]) == Decimal("0")
        assert DayTotals.charged([_sub("12.99"), _sub("10.75")]) == Decimal("23.74")
