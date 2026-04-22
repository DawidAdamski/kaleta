from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MonthlyReadinessResponse(BaseModel):
    """Persisted stage state for one (year, month)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    month: int
    stage_1_done: bool
    stage_2_done: bool
    stage_3_done: bool
    stage_4_done: bool
    ready_at: datetime.datetime | None = None

    @property
    def is_ready(self) -> bool:
        return (
            self.stage_1_done
            and self.stage_2_done
            and self.stage_3_done
            and self.stage_4_done
        )


class Stage1CloseLastMonth(BaseModel):
    """What the Close-last-month stage shows."""

    last_year: int
    last_month: int
    uncategorised_count: int


class Stage2IncomeRow(BaseModel):
    """One recurring income line with expected vs actual for the window."""

    planned_id: int
    name: str
    expected: Decimal
    actual: Decimal

    @property
    def delta(self) -> Decimal:
        return self.actual - self.expected


class Stage2ConfirmIncome(BaseModel):
    rows: list[Stage2IncomeRow] = Field(default_factory=list)


class Stage3CopyPreviewRow(BaseModel):
    category_id: int
    category_name: str
    amount: Decimal
    already_set: bool


class Stage3AllocateNewMonth(BaseModel):
    from_year: int
    from_month: int
    to_year: int
    to_month: int
    rows: list[Stage3CopyPreviewRow] = Field(default_factory=list)

    @property
    def new_count(self) -> int:
        return sum(1 for r in self.rows if not r.already_set)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.rows if r.already_set)


class Stage4PlannedRow(BaseModel):
    planned_id: int
    date: datetime.date
    name: str
    amount: Decimal
    account_name: str
    category_name: str | None
    seen: bool = False


class Stage4AcknowledgeBills(BaseModel):
    rows: list[Stage4PlannedRow] = Field(default_factory=list)

    @property
    def all_seen(self) -> bool:
        return all(r.seen for r in self.rows)
