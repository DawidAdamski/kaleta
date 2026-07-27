# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from kaleta.models.categorisation_rule import RuleMatchMode

__all__ = [
    "RuleMatchMode",
    "CategorisationRuleCreate",
    "CategorisationRuleUpdate",
    "CategorisationRuleResponse",
    "CategorisationRuleSuggestion",
]


class CategorisationRuleCreate(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=200)
    category_id: int
    match_mode: RuleMatchMode = RuleMatchMode.CONTAINS
    is_active: bool = True
    priority: int = 0


class CategorisationRuleUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = None
    match_mode: RuleMatchMode | None = None
    is_active: bool | None = None
    priority: int | None = None


class CategorisationRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    match_mode: RuleMatchMode
    category_id: int
    category_name: str | None = None
    is_active: bool
    priority: int


class CategorisationRuleSuggestion(BaseModel):
    """Offer to create a rule after repeated manual categorisations."""

    pattern: str
    category_id: int
    category_name: str
    match_count: int
