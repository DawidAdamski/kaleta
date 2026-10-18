# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "GiftCreate",
    "GiftPersonGroup",
    "GiftResponse",
    "GiftUpdate",
    "GiftsSummary",
]


class GiftBase(BaseModel):
    """Shared editable fields for a planned gift."""

    person: str = Field(..., min_length=1, max_length=100)
    occasion: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)


class GiftCreate(GiftBase):
    pass


class GiftUpdate(BaseModel):
    """All fields optional — PATCH semantics."""

    person: str | None = Field(default=None, min_length=1, max_length=100)
    occasion: str | None = Field(default=None, min_length=1, max_length=100)
    amount: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)


class GiftResponse(GiftBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    #: Bought once a ledger transaction is linked to it (``KAL-GFT-003``).
    bought: bool = False
    #: The sum of the linked transactions' amounts; ``None`` until bought.
    actual_cost: Decimal | None = None


class GiftPersonGroup(BaseModel):
    """Every gift planned for one person, newest first, with their subtotal."""

    person: str
    gifts: list[GiftResponse]
    subtotal: Decimal


class GiftsSummary(BaseModel):
    """The gift list grouped by person, plus the yearly total across everyone."""

    groups: list[GiftPersonGroup]
    yearly_total: Decimal
