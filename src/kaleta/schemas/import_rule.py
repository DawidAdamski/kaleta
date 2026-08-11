# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ImportRuleCreate",
    "ImportRuleUpdate",
    "ImportRuleResponse",
]


class ImportRuleCreate(BaseModel):
    filename_pattern: str = Field(..., min_length=1, max_length=200)
    account_id: int
    column_mapping: dict[str, Any] = Field(default_factory=dict)
    encoding: str | None = Field(default=None, max_length=40)
    delimiter: str | None = Field(default=None, max_length=8)
    is_active: bool = True


class ImportRuleUpdate(BaseModel):
    filename_pattern: str | None = Field(default=None, min_length=1, max_length=200)
    account_id: int | None = None
    column_mapping: dict[str, Any] | None = None
    encoding: str | None = None
    delimiter: str | None = None
    is_active: bool | None = None


class ImportRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename_pattern: str
    account_id: int
    account_name: str | None = None
    column_mapping: dict[str, Any]
    encoding: str | None = None
    delimiter: str | None = None
    is_active: bool
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
