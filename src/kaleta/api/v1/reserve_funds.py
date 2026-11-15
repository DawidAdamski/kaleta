# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.irregular_item import (
    IrregularFundPlan,
    IrregularItemCreate,
    IrregularItemResponse,
    IrregularItemUpdate,
)
from kaleta.schemas.reserve_fund import ReserveFundResponse
from kaleta.services.irregular_item_service import IrregularItemService
from kaleta.services.reserve_fund_service import ReserveFundService

_ITEM_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Fund not found, or the item is not in this fund"},
    422: {"description": "Invalid body, or the fund is not an irregular-expenses fund"},
}

router = APIRouter(prefix="/reserve-funds", tags=["Reserve funds"])


@router.get("/", response_model=list[ReserveFundResponse], summary="List reserve funds")
async def list_reserve_funds(
    include_archived: bool = Query(False, description="Include archived funds"),
    session: AsyncSession = Depends(get_session),
) -> list[ReserveFundResponse]:
    funds = await ReserveFundService(session).list(include_archived=include_archived)
    return [ReserveFundResponse.model_validate(fund) for fund in funds]


@router.get(
    "/{fund_id}/items",
    response_model=list[IrregularItemResponse],
    summary="List an irregular fund's items",
    description=(
        "The yearly costs an irregular-expenses fund saves for, by due month (a cost "
        "without one last), then by name. Each carries its `monthly_contribution`."
    ),
    responses=_ITEM_ERRORS,
)
async def list_irregular_items(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[IrregularItemResponse]:
    items = await IrregularItemService(session).items(fund_id)
    return [IrregularItemResponse.model_validate(item) for item in items]


@router.get(
    "/{fund_id}/plan",
    response_model=IrregularFundPlan,
    summary="Get an irregular fund's plan",
    description=(
        "The fund's items plus lines derived from other features (the yearly gifts "
        "total, on the oldest live irregular fund), their yearly and monthly totals, "
        "and the balance of the fund's account."
    ),
    responses=_ITEM_ERRORS,
)
async def get_irregular_plan(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> IrregularFundPlan:
    return await IrregularItemService(session).plan(fund_id)


@router.post(
    "/{fund_id}/items",
    response_model=IrregularItemResponse,
    status_code=201,
    summary="Add an item to an irregular fund",
    responses=_ITEM_ERRORS,
)
async def create_irregular_item(
    fund_id: int,
    data: IrregularItemCreate,
    session: AsyncSession = Depends(get_session),
) -> IrregularItemResponse:
    item = await IrregularItemService(session).create(fund_id, data)
    return IrregularItemResponse.model_validate(item)


@router.put(
    "/{fund_id}/items/{item_id}",
    response_model=IrregularItemResponse,
    summary="Update an irregular fund's item",
    description="Partially updates the item. Only fields in the body are changed.",
    responses=_ITEM_ERRORS,
)
async def update_irregular_item(
    fund_id: int,
    item_id: int,
    data: IrregularItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> IrregularItemResponse:
    item = await IrregularItemService(session).update(item_id, data, fund_id=fund_id)
    return IrregularItemResponse.model_validate(item)


@router.delete(
    "/{fund_id}/items/{item_id}",
    status_code=204,
    summary="Delete an irregular fund's item",
    responses=_ITEM_ERRORS,
)
async def delete_irregular_item(
    fund_id: int,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    await IrregularItemService(session).delete(item_id, fund_id=fund_id)
