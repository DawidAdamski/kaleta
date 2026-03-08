from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.asset import AssetType


class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: AssetType = AssetType.OTHER
    value: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    description: str = ""
    purchase_date: datetime.date | None = None
    purchase_price: Decimal | None = Field(default=None, decimal_places=2)


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AssetType | None = None
    value: Decimal | None = Field(default=None, decimal_places=2)
    description: str | None = None
    purchase_date: datetime.date | None = None
    purchase_price: Decimal | None = Field(default=None, decimal_places=2)


class AssetResponse(AssetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
