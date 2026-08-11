# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.import_rule import ImportRuleCreate, ImportRuleResponse, ImportRuleUpdate
from kaleta.services.import_rule_service import ImportRuleService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Import rule not found"}}

router = APIRouter(prefix="/import-rules", tags=["Import rules"])


def _to_response(rule: Any) -> ImportRuleResponse:
    return ImportRuleResponse(
        id=rule.id,
        filename_pattern=rule.filename_pattern,
        account_id=rule.account_id,
        account_name=rule.account.name if rule.account else None,
        column_mapping=dict(rule.column_mapping or {}),
        encoding=rule.encoding,
        delimiter=rule.delimiter,
        is_active=rule.is_active,
        last_used_at=rule.last_used_at,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("/", response_model=list[ImportRuleResponse], summary="List import rules")
async def list_import_rules(
    session: AsyncSession = Depends(get_session),
) -> list[ImportRuleResponse]:
    rules = await ImportRuleService(session).list()
    return [_to_response(rule) for rule in rules]


@router.post(
    "/",
    response_model=ImportRuleResponse,
    status_code=201,
    summary="Create an import rule",
)
async def create_import_rule(
    data: ImportRuleCreate,
    session: AsyncSession = Depends(get_session),
) -> ImportRuleResponse:
    rule = await ImportRuleService(session).create(data)
    return _to_response(rule)


@router.get(
    "/{rule_id}",
    response_model=ImportRuleResponse,
    summary="Get import rule by ID",
    responses=_404,
)
async def get_import_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
) -> ImportRuleResponse:
    rule = await ImportRuleService(session).get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Import rule not found")
    return _to_response(rule)


@router.put(
    "/{rule_id}",
    response_model=ImportRuleResponse,
    summary="Update an import rule",
    responses=_404,
)
async def update_import_rule(
    rule_id: int,
    data: ImportRuleUpdate,
    session: AsyncSession = Depends(get_session),
) -> ImportRuleResponse:
    rule = await ImportRuleService(session).update(rule_id, data)
    return _to_response(rule)


@router.delete(
    "/{rule_id}",
    status_code=204,
    summary="Delete an import rule",
    responses=_404,
)
async def delete_import_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    deleted = await ImportRuleService(session).delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Import rule not found")
