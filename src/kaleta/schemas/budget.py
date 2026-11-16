# SPDX-License-Identifier: AGPL-3.0-or-later
import math
from datetime import date as _date
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


class RealizationStatus(str, Enum):  # noqa: UP042
    ON_TRACK = "on_track"
    WARNING = "warning"
    OVER = "over"


class RealizationNoteKind(Enum):
    """The two things a schedule can say about a row whose bar looks wrong."""

    PAID_IN_FULL = "paid_in_full"
    PLANNED_ON = "planned_on"


class BudgetBase(BaseModel):
    category_id: int
    amount: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000, le=2100)


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=Decimal("0"), decimal_places=2)
    month: int | None = Field(default=None, ge=1, le=12)
    year: int | None = Field(default=None, ge=2000, le=2100)

    @model_validator(mode="after")
    def month_and_year_together(self) -> "BudgetUpdate":
        if (self.month is None) != (self.year is None):
            raise ValueError("Provide both 'month' and 'year' together, or neither.")
        return self


class BudgetResponse(BudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class RealizationNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: RealizationNoteKind
    date: _date
    amount: Decimal


class BudgetRealizationRow(BaseModel):
    """Serialisable form of a CategoryRealization row."""

    model_config = ConfigDict(from_attributes=True)

    category_id: int
    category_name: str
    parent_id: int | None = None
    parent_name: str | None = None
    planned: Decimal
    actual: Decimal
    remaining: Decimal
    elapsed_pct: float
    #: ``None`` for spending with no plan: the service's infinity is not JSON.
    used_pct: float | None
    pace_delta: float | None
    status: RealizationStatus
    note: RealizationNoteResponse | None = None

    @field_validator("used_pct", "pace_delta", mode="before")
    @classmethod
    def _finite_or_none(cls, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value


class BudgetRealizationTotals(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planned: Decimal
    actual: Decimal
    remaining: Decimal
    used_pct: float
    over: int
    rows: int


class BudgetRealizationResponse(BaseModel):
    year: int
    month: int
    as_of: _date
    totals: BudgetRealizationTotals
    categories: list[BudgetRealizationRow]


class BudgetSummaryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    category_name: str
    budget_amount: Decimal
    actual_amount: Decimal
    remaining: Decimal
    percent_used: float
    over_budget: bool


class BudgetSummaryResponse(BaseModel):
    start: _date
    end: _date
    categories: list[BudgetSummaryRow]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def budget_total(self) -> Decimal:
        return sum((c.budget_amount for c in self.categories), Decimal("0"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def actual_total(self) -> Decimal:
        return sum((c.actual_amount for c in self.categories), Decimal("0"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining_total(self) -> Decimal:
        return self.budget_total - self.actual_total


class BudgetCopyForwardRequest(BaseModel):
    from_year: int = Field(..., ge=2000, le=2100)
    from_month: int = Field(..., ge=1, le=12)
    to_year: int = Field(..., ge=2000, le=2100)
    to_month: int = Field(..., ge=1, le=12)
    #: Replace amounts the target month already has; by default they are kept.
    overwrite: bool = False

    @model_validator(mode="after")
    def _different_months(self) -> "BudgetCopyForwardRequest":
        if (self.from_year, self.from_month) == (self.to_year, self.to_month):
            raise ValueError("The source and target month must differ.")
        return self


class BudgetBulkUpsertRequest(BaseModel):
    entries: list[BudgetCreate] = Field(..., min_length=1, max_length=1000)


class BudgetWriteCountResponse(BaseModel):
    written: int
