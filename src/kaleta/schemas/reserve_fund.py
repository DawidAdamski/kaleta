from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kaleta.models.reserve_fund import ReserveFundBackingMode, ReserveFundKind


class ReserveFundBase(BaseModel):
    """Shared editable fields for a reserve fund."""

    name: str = Field(..., min_length=1, max_length=100)
    kind: ReserveFundKind
    target_amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)
    backing_mode: ReserveFundBackingMode = ReserveFundBackingMode.ACCOUNT
    backing_account_id: int | None = None
    backing_category_id: int | None = None
    emergency_multiplier: int | None = Field(default=None, ge=1, le=24)

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
        return self


class ReserveFundCreate(ReserveFundBase):
    pass


class ReserveFundUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)
    backing_mode: ReserveFundBackingMode | None = None
    backing_account_id: int | None = None
    backing_category_id: int | None = None
    emergency_multiplier: int | None = Field(default=None, ge=1, le=24)


class ReserveFundResponse(ReserveFundBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ReserveFundWithProgress(ReserveFundResponse):
    """A fund plus derived progress metrics for the dashboard/wizard card."""

    current_balance: Decimal
    progress_pct: Decimal = Field(..., description="0.00–1.00+, clamp in UI if desired.")
    months_of_coverage: Decimal | None = None
