# SPDX-License-Identifier: AGPL-3.0-or-later
"""The annual review's three steps (``budgets-annual-review``, ``KAL-ANR``)."""

from __future__ import annotations

import enum
from decimal import Decimal

from pydantic import BaseModel, Field

from kaleta.schemas.yearly_plan import YearlyPlanPayload

__all__ = [
    "AnnualCarry",
    "AnnualCategoryYear",
    "AnnualSummary",
    "CarryCategory",
    "Commitment",
    "CommitmentKind",
]


class AnnualCategoryYear(BaseModel):
    """One expense category over one year: what was planned, what was spent."""

    category_id: int
    name: str
    planned: Decimal
    actual: Decimal

    @property
    def difference(self) -> Decimal:
        """Planned minus actual: positive is money the plan left unspent."""
        return self.planned - self.actual


class AnnualSummary(BaseModel):
    """Step 1: the year in numbers."""

    year: int
    rows: list[AnnualCategoryYear]
    planned_total: Decimal
    actual_total: Decimal


class CarryCategory(BaseModel):
    """Step 2, one row: a category's plan this year, its adjustment, and next year's."""

    category_id: int
    name: str
    planned: Decimal
    pct: Decimal = Decimal("0")
    next_amount: Decimal


class AnnualCarry(BaseModel):
    """Step 2: next year's payload, built from this year's, and what it gives per category."""

    year: int
    rows: list[CarryCategory]
    payload: YearlyPlanPayload
    #: ``year + 1`` already has a yearly plan, which applying replaces.
    replaces_plan: bool


class CommitmentKind(enum.StrEnum):
    SUBSCRIPTION = "subscription"
    IRREGULAR_ITEM = "irregular_item"


class Commitment(BaseModel):
    """Step 3, one row: a subscription or an irregular-fund item, to keep, adjust or drop."""

    kind: CommitmentKind
    id: int
    name: str
    #: What "adjust" edits: a subscription's charge, an item's yearly amount.
    amount: Decimal = Field(..., gt=0)
    yearly: Decimal
