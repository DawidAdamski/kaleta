from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
