from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CurrencyRateCreate(BaseModel):
    date: datetime.date
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: Decimal = Field(..., gt=Decimal("0"))


class CurrencyRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime.date
    from_currency: str
    to_currency: str
    rate: Decimal
    created_at: datetime.datetime
    updated_at: datetime.datetime
