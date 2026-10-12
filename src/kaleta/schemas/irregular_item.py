# SPDX-License-Identifier: AGPL-3.0-or-later
"""The irregular-expenses fund's items and its funding plan (``funds-irregular-items``)."""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from kaleta.core.irregular import monthly_contribution

__all__ = [
    "IrregularEntryKind",
    "IrregularFundEntry",
    "IrregularFundPlan",
    "IrregularFundingCreate",
    "IrregularItemCreate",
    "IrregularItemResponse",
    "IrregularItemUpdate",
    "IrregularPaymentCreate",
]


class IrregularItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    yearly_amount: Decimal = Field(..., gt=0, decimal_places=2)
    due_month: int | None = Field(default=None, ge=1, le=12)
    category_id: int | None = None


class IrregularItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    yearly_amount: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    due_month: int | None = Field(default=None, ge=1, le=12)
    category_id: int | None = None


class IrregularItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fund_id: int
    name: str
    yearly_amount: Decimal
    due_month: int | None
    category_id: int | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def monthly_contribution(self) -> Decimal:
        """A tenth of the yearly amount (``kaleta.core.irregular``)."""
        return monthly_contribution(self.yearly_amount)


class IrregularFundPlan(BaseModel):
    """One irregular fund's items, and what they ask for each month."""

    fund_id: int
    fund_name: str
    backing_account_id: int | None
    items: list[IrregularItemResponse]
    yearly_total: Decimal
    monthly_total: Decimal
    #: What the fund holds: its account's balance, from the ledger.
    balance: Decimal = Decimal("0.00")


class IrregularFundingCreate(BaseModel):
    """Accepting the funding proposal: a monthly transfer into the fund's account."""

    from_account_id: int
    start_date: datetime.date


class IrregularPaymentCreate(BaseModel):
    """A payment out of the fund: of one item, or (``item_id`` ``None``) an unplanned cost."""

    item_id: int | None = None
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    date: datetime.date
    description: str = Field(default="", max_length=500)
    #: ``None``: the item's own category.
    category_id: int | None = None


class IrregularEntryKind(enum.StrEnum):
    CONTRIBUTION = "contribution"
    PAYMENT = "payment"
    UNPLANNED = "unplanned"
    WITHDRAWAL = "withdrawal"


class IrregularFundEntry(BaseModel):
    """One row of the fund's history: a movement on its account."""

    transaction_id: int
    date: datetime.date
    description: str
    #: Signed: money into the fund is positive, out of it negative.
    amount: Decimal
    kind: IrregularEntryKind
    item_id: int | None = None
    item_name: str | None = None
