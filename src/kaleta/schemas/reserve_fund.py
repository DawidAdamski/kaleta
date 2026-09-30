# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind

__all__ = [
    "GoalClose",
    "GoalContribution",
    "ReserveFundBackingMode",
    "ReserveFundCreate",
    "ReserveFundKind",
    "ReserveFundResponse",
    "ReserveFundUpdate",
    "ReserveFundWithProgress",
]


class ReserveFundBase(BaseModel):
    """Shared editable fields for a reserve fund."""

    name: str = Field(..., min_length=1, max_length=100)
    kind: ReserveFundKind
    target_amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)
    backing_mode: ReserveFundBackingMode = ReserveFundBackingMode.ACCOUNT
    backing_account_id: int | None = None
    backing_category_id: int | None = None
    emergency_multiplier: int | None = Field(default=None, ge=1, le=24)
    #: Target = multiplier × 12-month average monthly spend instead of
    #: ``target_amount``. Needs a multiplier to multiply by.
    target_from_spending: bool = False
    #: When a savings goal should be full. Only a goal (kind ``vacation``)
    #: has one; it drives the monthly pace on its card.
    target_date: datetime.date | None = None

    @model_validator(mode="after")
    def _check_backing_ref(self) -> ReserveFundBase:
        if self.backing_mode == ReserveFundBackingMode.ACCOUNT:
            if self.backing_account_id is None:
                raise ValueError("backing_account_id is required when backing_mode=account")
            if self.backing_category_id is not None:
                raise ValueError("backing_category_id must be null when backing_mode=account")
        else:
            if self.backing_category_id is None:
                raise ValueError("backing_category_id is required when backing_mode=envelope")
            if self.backing_account_id is not None:
                raise ValueError("backing_account_id must be null when backing_mode=envelope")
        if self.target_from_spending and self.emergency_multiplier is None:
            raise ValueError("emergency_multiplier is required when target_from_spending is set")
        if self.target_date is not None and self.kind != ReserveFundKind.VACATION:
            raise ValueError("Only a savings goal (kind=vacation) has a target_date")
        return self


class ReserveFundCreate(ReserveFundBase):
    pass


class ReserveFundUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: ReserveFundKind | None = None
    target_amount: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)
    backing_mode: ReserveFundBackingMode | None = None
    backing_account_id: int | None = None
    backing_category_id: int | None = None
    emergency_multiplier: int | None = Field(default=None, ge=1, le=24)
    target_from_spending: bool | None = None
    target_date: datetime.date | None = None


class ReserveFundResponse(ReserveFundBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_archived: bool = False
    archived_at: datetime.datetime | None = None


class ReserveFundWithProgress(ReserveFundResponse):
    """A fund plus derived progress metrics for the dashboard/wizard card."""

    current_balance: Decimal
    progress_pct: Decimal = Field(..., description="0.00–1.00+, clamp in UI if desired.")
    months_of_coverage: Decimal | None = None
    #: Goals with a target date only: whole months left, and what must go in
    #: each of them to reach the target (zero once it is reached).
    months_left: int | None = None
    monthly_pace: Decimal | None = None


class GoalContribution(BaseModel):
    """Money moved into a goal's backing account from another account."""

    amount: Decimal = Field(..., gt=Decimal("0"), decimal_places=2)
    from_account_id: int
    date: datetime.date
    description: str = Field(default="", max_length=500)


class GoalClose(BaseModel):
    """Close a goal: archive it and, optionally, move its balance out."""

    release_to_account_id: int | None = None
    date: datetime.date
    description: str = Field(default="", max_length=500)
