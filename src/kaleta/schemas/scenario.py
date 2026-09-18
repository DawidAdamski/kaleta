# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas for the what-if scenario simulator."""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import BaseModel, model_validator

from kaleta.schemas.planned_transaction import RecurrenceFrequency


class ScenarioDeltaKind(str, enum.Enum):  # noqa: UP042
    """The three things a reader can ask "what if" about."""

    #: Income rises or falls from a date onward, as a percentage or an amount.
    INCOME_CHANGE = "income_change"
    #: A single purchase or windfall on one date.
    ONE_OFF = "one_off"
    #: A new bill or a new income stream, repeating on a cadence.
    RECURRING = "recurring"


#: How many times a cadence fires in a month, for turning a repeating delta
#: into the monthly figure the runway is measured in. ``ONCE`` never repeats,
#: so it contributes nothing to a monthly rate.
_PER_MONTH: dict[RecurrenceFrequency, Decimal] = {
    RecurrenceFrequency.ONCE: Decimal("0"),
    RecurrenceFrequency.DAILY: Decimal("30"),
    RecurrenceFrequency.WEEKLY: Decimal("52") / Decimal("12"),
    RecurrenceFrequency.BIWEEKLY: Decimal("26") / Decimal("12"),
    RecurrenceFrequency.MONTHLY: Decimal("1"),
    RecurrenceFrequency.QUARTERLY: Decimal("1") / Decimal("3"),
    RecurrenceFrequency.YEARLY: Decimal("1") / Decimal("12"),
}


def occurrences_per_month(cadence: RecurrenceFrequency) -> Decimal:
    """How often *cadence* fires in an average month."""
    return _PER_MONTH[cadence]


class ScenarioDelta(BaseModel):
    """One change laid over the baseline forecast.

    ``amount`` is signed the way the ledger is: negative takes money out
    (a purchase, a new bill), positive puts it in (a windfall, a raise).
    An income change may instead carry ``percent``, which is read against
    the income the account actually earned — the balance series alone
    cannot say what a third of someone's income is.
    """

    kind: ScenarioDeltaKind
    label: str
    start_date: datetime.date
    amount: Decimal | None = None
    percent: Decimal | None = None
    cadence: RecurrenceFrequency | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> ScenarioDelta:
        """Reject a delta that carries a field its kind cannot use.

        Silently ignoring an extra ``percent`` or ``cadence`` would let a
        caller believe a scenario it never built: "40,000 off, −30%" would
        apply only the 40,000, and say nothing about the rest.
        """
        if self.kind is ScenarioDeltaKind.INCOME_CHANGE:
            if (self.amount is None) == (self.percent is None):
                raise ValueError("An income change needs exactly one of amount or percent")
        else:
            if self.amount is None:
                raise ValueError(f"A {self.kind.value} delta needs an amount")
            if self.percent is not None:
                raise ValueError(f"A {self.kind.value} delta is an amount, not a percentage")
        if self.kind is ScenarioDeltaKind.RECURRING:
            if self.cadence is None:
                raise ValueError("A recurring delta needs a cadence")
        elif self.cadence is not None:
            raise ValueError(f"A {self.kind.value} delta does not repeat, so it has no cadence")
        if self.percent is not None and self.percent <= Decimal("-100"):
            raise ValueError("Income cannot fall by more than 100%")
        return self


class ScenarioVerdict(BaseModel):
    """The sentence above the chart: what the deltas did, in figures.

    Every ``…_before`` reads the untouched baseline, so a reader can see
    the size of the change rather than only where it landed.
    """

    #: Net change to monthly cashflow, positive when the scenario leaves
    #: more money each month.
    monthly_delta: Decimal
    balance_before: Decimal | None
    balance_after: Decimal | None
    #: First day the projected balance goes below zero, baseline and after.
    #: ``None`` when it never does — which is the answer worth having.
    first_negative_before: datetime.date | None
    first_negative_after: datetime.date | None
    #: Months of essential spending the emergency funds cover. ``None``
    #: when nothing is set aside or nothing has been spent to measure.
    runway_before: Decimal | None
    runway_after: Decimal | None

    @property
    def goes_negative(self) -> bool:
        """The scenario runs the balance out when the baseline did not."""
        return self.first_negative_after is not None and self.first_negative_before is None


__all__ = [
    "ScenarioDelta",
    "ScenarioDeltaKind",
    "ScenarioVerdict",
    "occurrences_per_month",
]
