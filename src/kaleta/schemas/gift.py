# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schemas for the gift grid: people (rows), occasions (columns), cells."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "GiftCellResponse",
    "GiftCellSet",
    "GiftGrid",
    "GiftLaneResponse",
    "GiftName",
    "GiftsSummary",
]

#: The longest person or occasion name the grid accepts.
GIFT_NAME_MAX = 100
#: The longest note a cell holds ("Other: wedding anniversary").
GIFT_NOTE_MAX = 200


class GiftName(BaseModel):
    """A new or renamed person or occasion."""

    name: str = Field(..., min_length=1, max_length=GIFT_NAME_MAX)


class GiftCellSet(BaseModel):
    """What one cell should hold. ``amount=None`` empties (deletes) the cell."""

    amount: Decimal | None = Field(default=None, ge=Decimal("0"), decimal_places=2)
    note: str | None = Field(default=None, max_length=GIFT_NOTE_MAX)


class GiftLaneResponse(BaseModel):
    """A person (a row) or an occasion (a column) of the grid."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: int
    archived: bool


class GiftCellResponse(BaseModel):
    id: int
    person_id: int
    occasion_id: int
    amount: Decimal
    note: str | None = None
    #: Bought once a ledger expense is linked to the cell (``KAL-GFT-003``).
    bought: bool = False
    #: The sum of the linked expenses; ``None`` until bought.
    actual_cost: Decimal | None = None


class GiftGrid(BaseModel):
    """One year of the grid, with every total the page shows."""

    year: int
    people: list[GiftLaneResponse]
    occasions: list[GiftLaneResponse]
    cells: list[GiftCellResponse]
    #: Per person id, the sum of that row's cells.
    row_totals: dict[int, Decimal]
    #: Per occasion id, the sum of that column's cells.
    column_totals: dict[int, Decimal]
    total: Decimal
    #: Whether ``year - 1`` has cells to copy (offered only for an empty year).
    previous_year_has_cells: bool


class GiftsSummary(BaseModel):
    """What the irregular fund reads: one year's gift total."""

    year: int
    yearly_total: Decimal
