from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SavedReportCreate(BaseModel):
    name: str
    config: str  # JSON string


class SavedReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    config: str
