# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas for the "pay yourself a salary" wizard panel.

Irregular income is smoothed into one fixed monthly transfer. The proposal
is derived from a recent window of *complete* months; the surplus above the
salary is what accumulates as the buffer.
"""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SalaryBasis",
    "MonthlyIncome",
    "BufferPoint",
    "SalaryProposal",
    "SalaryPlanCreate",
]


class SalaryBasis(str, enum.Enum):  # noqa: UP042
    """Which statistic of the income window feeds the proposed salary."""

    WORST = "worst"
    P25 = "p25"
    MEDIAN = "median"


class MonthlyIncome(BaseModel):
    """Total non-transfer income booked in one complete calendar month."""

    model_config = ConfigDict(frozen=True)

    year: int
    month: int = Field(ge=1, le=12)
    total: Decimal

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


class BufferPoint(BaseModel):
    """One month of the buffer replay: what the salary would have left over."""

    model_config = ConfigDict(frozen=True)

    year: int
    month: int = Field(ge=1, le=12)
    income: Decimal
    surplus: Decimal  # income − salary; negative when the month underpays
    buffer: Decimal  # running sum of ``surplus`` from the window's start

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


class SalaryProposal(BaseModel):
    """Income variability of the window plus the salary it supports."""

    model_config = ConfigDict(frozen=True)

    window_months: int
    months: list[MonthlyIncome] = Field(default_factory=list)
    worst: Decimal = Decimal("0.00")
    best: Decimal = Decimal("0.00")
    median: Decimal = Decimal("0.00")
    p25: Decimal = Decimal("0.00")
    basis: SalaryBasis = SalaryBasis.WORST
    salary: Decimal = Decimal("0.00")
    projection: list[BufferPoint] = Field(default_factory=list)
    has_enough_history: bool = False
    currencies: list[str] = Field(default_factory=list)

    @property
    def is_multi_currency(self) -> bool:
        return len(self.currencies) > 1

    @property
    def final_buffer(self) -> Decimal:
        return self.projection[-1].buffer if self.projection else Decimal("0.00")


class SalaryPlanCreate(BaseModel):
    """Turn an accepted proposal into a recurring self-transfer."""

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    from_account_id: int
    to_account_id: int
    start_date: datetime.date
