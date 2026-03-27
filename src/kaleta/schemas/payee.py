from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PayeeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


class PayeeCreate(PayeeBase):
    pass


class PayeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


class PayeeMerge(BaseModel):
    keep_id: int = Field(..., description="ID of the payee to keep")
    merge_ids: list[int] = Field(..., min_length=1, description="IDs of payees to merge into keep_id")


class PayeeResponse(PayeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
