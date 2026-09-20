# SPDX-License-Identifier: AGPL-3.0-or-later
"""What one day of the payment calendar comes to.

A day's figures are assembled from two sources that do not know about each
other — the planned occurrences `PlannedTransactionService` aggregates, and
the subscription charges `WizardProjectionService` projects — and three
readers ask the same question of them: the cell in the month grid, the day
sheet's Out, the day sheet's Net. They lived in the view, next to the cell
that drew them, and the sheet drifted out of step with the grid for exactly
that reason: a day drawn `-12.99` opened onto `Out 0.00`.

Here instead, where the aggregates are, so the rule is one rule and a test
can reach it without rendering anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from kaleta.schemas.wizard_projections import SubscriptionCharge
from kaleta.services.planned_transaction_service import DayAggregate


def charged(subscriptions: Sequence[SubscriptionCharge]) -> Decimal:
    """What the day's projected subscription charges come to."""
    return sum((s.amount for s in subscriptions), Decimal("0"))


def day_in(cell: DayAggregate | None) -> Decimal:
    """What arrives on the day. A subscription charge is never one of them."""
    return cell.inflow if cell else Decimal("0")


def day_out(cell: DayAggregate | None, subscriptions: Sequence[SubscriptionCharge] = ()) -> Decimal:
    """What leaves on the day, subscription charges included."""
    return (cell.outflow if cell else Decimal("0")) + charged(subscriptions)


def day_net(cell: DayAggregate | None, subscriptions: Sequence[SubscriptionCharge] = ()) -> Decimal:
    """What the day comes to: what arrived, less everything that left."""
    return (cell.net if cell else Decimal("0")) - charged(subscriptions)


__all__ = ["charged", "day_in", "day_net", "day_out"]
