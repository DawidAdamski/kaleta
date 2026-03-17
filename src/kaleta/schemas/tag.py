from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TagCreate(BaseModel):
    name: str = Field(..., max_length=50)
    color: str | None = Field(default=None, max_length=7)
    icon: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=7)
    icon: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)


class TagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None
    icon: str | None
    description: str | None
