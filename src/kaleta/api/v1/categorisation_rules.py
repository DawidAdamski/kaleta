# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/categorisation-rules`` — description/payee → category rules for imports.

Not ``/import-rules``, which maps a statement's filename to an account.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import NotFoundError
from kaleta.models.categorisation_rule import CategorisationRule
from kaleta.schemas.categorisation_rule import (
    CategorisationRuleCreate,
    CategorisationRuleResponse,
    CategorisationRuleSuggestion,
    CategorisationRuleSuggestionRequest,
    CategorisationRuleUpdate,
)
from kaleta.services.rule_service import RuleService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Rule not found"}}
_CATEGORY_404: dict[int | str, dict[str, Any]] = {
    404: {"description": "The rule, or its category, does not exist"}
}
_422: dict[int | str, dict[str, Any]] = {
    422: {"description": "A blank pattern, or a required field set to null"}
}

router = APIRouter(prefix="/categorisation-rules", tags=["Categorisation rules"])


def _to_response(rule: CategorisationRule) -> CategorisationRuleResponse:
    return CategorisationRuleResponse(
        id=rule.id,
        pattern=rule.pattern,
        match_mode=rule.match_mode,
        category_id=rule.category_id,
        category_name=rule.category.name if rule.category else None,
        is_active=rule.is_active,
        priority=rule.priority,
    )


@router.get(
    "/",
    response_model=list[CategorisationRuleResponse],
    summary="List categorisation rules",
    description="Highest priority first. `active_only` hides switched-off rules.",
)
async def list_rules(
    active_only: bool = Query(False, description="Only rules that are switched on"),
    session: AsyncSession = Depends(get_session),
) -> list[CategorisationRuleResponse]:
    rules = await RuleService(session).list(active_only=active_only)
    return [_to_response(rule) for rule in rules]


@router.post(
    "/",
    response_model=CategorisationRuleResponse,
    status_code=201,
    summary="Create a categorisation rule",
    description=(
        "An import files a row whose payee or description contains `pattern` "
        "(case-insensitive) under `category_id`. Two rules may share a pattern; "
        "the higher priority wins."
    ),
    responses={404: {"description": "The category does not exist"}, **_422},
)
async def create_rule(
    data: CategorisationRuleCreate, session: AsyncSession = Depends(get_session)
) -> CategorisationRuleResponse:
    return _to_response(await RuleService(session).create(data))


@router.post(
    "/suggestions",
    response_model=CategorisationRuleSuggestion | None,
    summary="Ask whether a categorisation is worth a rule",
    description=(
        "Given a categorisation made by hand, returns the rule the app would offer once "
        "the same pattern has gone to that category four times, or `null`. Creates "
        "nothing. A POST so that payee names and descriptions stay out of URLs."
    ),
)
async def suggest_rule(
    data: CategorisationRuleSuggestionRequest, session: AsyncSession = Depends(get_session)
) -> CategorisationRuleSuggestion | None:
    return await RuleService(session).suggest_from_corrections(
        payee_name=data.payee_name, description=data.description, category_id=data.category_id
    )


@router.get(
    "/{rule_id}",
    response_model=CategorisationRuleResponse,
    summary="Get a categorisation rule",
    responses=_404,
)
async def get_rule(
    rule_id: int, session: AsyncSession = Depends(get_session)
) -> CategorisationRuleResponse:
    rule = await RuleService(session).get(rule_id)
    if rule is None:
        raise NotFoundError(f"Categorisation rule {rule_id} not found")
    return _to_response(rule)


@router.put(
    "/{rule_id}",
    response_model=CategorisationRuleResponse,
    summary="Update a categorisation rule",
    description="Partially updates the rule. Only fields in the body change.",
    responses={**_CATEGORY_404, **_422},
)
async def update_rule(
    rule_id: int, data: CategorisationRuleUpdate, session: AsyncSession = Depends(get_session)
) -> CategorisationRuleResponse:
    return _to_response(await RuleService(session).update(rule_id, data))


@router.delete(
    "/{rule_id}", status_code=204, summary="Delete a categorisation rule", responses=_404
)
async def delete_rule(rule_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await RuleService(session).delete(rule_id):
        raise NotFoundError(f"Categorisation rule {rule_id} not found")
