from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class IncomeLine(BaseModel):
    """One income source line: name + yearly total."""

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)


class FixedLine(BaseModel):
    """A fixed cost line: name + yearly total + optional category."""

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)
    category_id: int | None = None


class VariableLine(BaseModel):
    """A variable envelope: name + yearly target + required category."""

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)
    category_id: int


class ReserveLine(BaseModel):
    """A reserve fund contribution line (reserved for Safety Funds work)."""

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., ge=Decimal("0"), decimal_places=2)


class YearlyPlanPayload(BaseModel):
    """Editable shape of a yearly plan — what the view sends in and reads back."""

    year: int = Field(..., ge=2000, le=2100)
    income_lines: list[IncomeLine] = []
    fixed_lines: list[FixedLine] = []
    variable_lines: list[VariableLine] = []
    reserves_lines: list[ReserveLine] = []


class YearlyPlanResponse(YearlyPlanPayload):
    model_config = ConfigDict(from_attributes=True)

    id: int


class BudgetDiffEntry(BaseModel):
    """One cell of the diff preview shown before Apply overwrites Budget rows."""

    category_id: int
    category_name: str
    month: int
    current: Decimal | None
    proposed: Decimal


class BudgetDiff(BaseModel):
    """Grouped diff — added, updated, unchanged."""

    added: list[BudgetDiffEntry] = []
    updated: list[BudgetDiffEntry] = []
    unchanged_count: int = 0
