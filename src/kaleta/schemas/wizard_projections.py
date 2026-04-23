from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["subscription", "planned", "reserve", "loan"]


class PulledRow(BaseModel):
    """A read-only row pulled from another wizard panel into this one."""

    model_config = ConfigDict(frozen=True)

    source_kind: SourceKind
    source_id: int
    label: str
    amount: Decimal  # monthly-equivalent when projected into a monthly view
    cadence: str  # free-text for tooltip ("monthly", "annual / 12", etc.)
    href: str | None = None  # where to click to edit the source record


class BudgetBuilderProjection(BaseModel):
    """Rows from other panels that the Budget Builder should surface."""

    income: list[PulledRow] = Field(default_factory=list)
    fixed: list[PulledRow] = Field(default_factory=list)
    variable: list[PulledRow] = Field(default_factory=list)
    reserves: list[PulledRow] = Field(default_factory=list)

    def section_monthly_total(self, section: str) -> Decimal:
        rows = getattr(self, section)
        return sum((r.amount for r in rows), Decimal("0.00"))


class SubscriptionCharge(BaseModel):
    """One projected subscription renewal inside a calendar window."""

    model_config = ConfigDict(frozen=True)

    date: datetime.date
    subscription_id: int
    name: str
    amount: Decimal


class PaymentCalendarProjection(BaseModel):
    subscription_charges: list[SubscriptionCharge] = Field(default_factory=list)


__all__ = [
    "BudgetBuilderProjection",
    "PaymentCalendarProjection",
    "PulledRow",
    "SourceKind",
    "SubscriptionCharge",
]
