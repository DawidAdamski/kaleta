from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.institution import InstitutionType


class InstitutionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: InstitutionType = InstitutionType.BANK
    color: str | None = Field(default=None, max_length=7)
    website: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    logo_path: str | None = Field(default=None, max_length=255)


class InstitutionCreate(InstitutionBase):
    pass


class InstitutionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: InstitutionType | None = None
    color: str | None = Field(default=None, max_length=7)
    website: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    logo_path: str | None = Field(default=None, max_length=255)


class InstitutionResponse(InstitutionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
