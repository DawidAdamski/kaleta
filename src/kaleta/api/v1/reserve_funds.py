# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import NotFoundError
from kaleta.models.reserve_fund import ReserveFund
from kaleta.schemas.irregular_item import (
    IrregularFundPlan,
    IrregularItemCreate,
    IrregularItemResponse,
    IrregularItemUpdate,
)
from kaleta.schemas.reserve_fund import (
    GoalClose,
    GoalContribution,
    ReserveFundCreate,
    ReserveFundResponse,
    ReserveFundUpdate,
    ReserveFundWithProgress,
)
from kaleta.services.irregular_item_service import IrregularItemService
from kaleta.services.reserve_fund_service import ReserveFundService

_ITEM_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Fund not found, or the item is not in this fund"},
    422: {"description": "Invalid body, or the fund is not an irregular-expenses fund"},
}

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Reserve fund not found"}}
_422: dict[int | str, dict[str, Any]] = {
    422: {
        "description": (
            "Invalid body, a backing account or category that does not exist, or a "
            "change that would leave the fund invalid (a required field set to null, "
            "a backing_mode without its reference, a target_date on a non-goal)"
        )
    }
}
_GOAL_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "Reserve fund not found, or the other account does not exist"},
    422: {
        "description": (
            "The fund is not a savings goal (kind vacation), is closed, or has no backing "
            "account; or the two accounts are the same or use different currencies"
        )
    },
}

router = APIRouter(prefix="/reserve-funds", tags=["Reserve funds"])


def _fund_or_404(fund: ReserveFund | None, fund_id: int) -> ReserveFundResponse:
    if fund is None:
        raise NotFoundError(f"Reserve fund {fund_id} not found")
    return ReserveFundResponse.model_validate(fund)


async def _progress_or_404(service: ReserveFundService, fund_id: int) -> ReserveFundWithProgress:
    fund = await service.get(fund_id)
    if fund is None:
        raise NotFoundError(f"Reserve fund {fund_id} not found")
    return await service.with_progress(fund)


@router.get("/", response_model=list[ReserveFundResponse], summary="List reserve funds")
async def list_reserve_funds(
    include_archived: bool = Query(False, description="Include archived funds"),
    session: AsyncSession = Depends(get_session),
) -> list[ReserveFundResponse]:
    funds = await ReserveFundService(session).list(include_archived=include_archived)
    return [ReserveFundResponse.model_validate(fund) for fund in funds]


@router.post(
    "/",
    response_model=ReserveFundResponse,
    status_code=201,
    summary="Create a reserve fund or savings goal",
    description=(
        "Creates an emergency, irregular-expenses or savings-goal fund. A savings goal "
        "is kind `vacation` and may carry a `target_date`. `backing_mode=account` needs "
        "`backing_account_id`; `envelope` needs `backing_category_id`."
    ),
    responses=_422,
)
async def create_reserve_fund(
    data: ReserveFundCreate,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundResponse:
    fund = await ReserveFundService(session).create(data)
    return ReserveFundResponse.model_validate(fund)


@router.get(
    "/{fund_id}",
    response_model=ReserveFundWithProgress,
    summary="Get a reserve fund with its progress",
    description=(
        "The fund, archived or not, with `current_balance` and `progress_pct`; "
        "`months_of_coverage` for an emergency fund; `months_left` and `monthly_pace` "
        "for a goal with a target date."
    ),
    responses=_404,
)
async def get_reserve_fund(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundWithProgress:
    return await _progress_or_404(ReserveFundService(session), fund_id)


@router.put(
    "/{fund_id}",
    response_model=ReserveFundResponse,
    summary="Update a reserve fund",
    description=(
        "Partially updates the fund. Only fields in the body change, and the result "
        "must still be a valid fund. Changing a goal to another kind clears its "
        "target_date."
    ),
    responses={**_404, **_422},
)
async def update_reserve_fund(
    fund_id: int,
    data: ReserveFundUpdate,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundResponse:
    return _fund_or_404(await ReserveFundService(session).update(fund_id, data), fund_id)


@router.delete(
    "/{fund_id}",
    status_code=204,
    summary="Delete a reserve fund",
    description=(
        "Deletes the fund. An irregular-expenses fund's items go with it. "
        "Transactions, including a goal's contributions, are never touched."
    ),
    responses=_404,
)
async def delete_reserve_fund(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await ReserveFundService(session).delete(fund_id):
        raise NotFoundError(f"Reserve fund {fund_id} not found")


@router.post(
    "/{fund_id}/archive",
    response_model=ReserveFundResponse,
    summary="Archive a reserve fund",
    description="Hides the fund from the default list. No money moves.",
    responses=_404,
)
async def archive_reserve_fund(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundResponse:
    return _fund_or_404(await ReserveFundService(session).archive(fund_id), fund_id)


@router.post(
    "/{fund_id}/unarchive",
    response_model=ReserveFundResponse,
    summary="Unarchive a reserve fund",
    responses=_404,
)
async def unarchive_reserve_fund(
    fund_id: int,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundResponse:
    return _fund_or_404(await ReserveFundService(session).unarchive(fund_id), fund_id)


@router.post(
    "/{fund_id}/contribute",
    response_model=ReserveFundWithProgress,
    summary="Contribute to a savings goal",
    description=(
        "Records a transfer of `amount` from `from_account_id` into the goal's backing "
        "account, and returns the goal's new progress."
    ),
    responses=_GOAL_ERRORS,
)
async def contribute_to_goal(
    fund_id: int,
    data: GoalContribution,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundWithProgress:
    service = ReserveFundService(session)
    await service.contribute(fund_id, data)
    return await _progress_or_404(service, fund_id)


@router.post(
    "/{fund_id}/close",
    response_model=ReserveFundResponse,
    summary="Close a savings goal",
    description=(
        "Archives the goal. With `release_to_account_id`, a positive balance is first "
        "moved there by a transfer; without it, no money moves."
    ),
    responses=_GOAL_ERRORS,
)
async def close_goal(
    fund_id: int,
    data: GoalClose,
    session: AsyncSession = Depends(get_session),
) -> ReserveFundResponse:
    fund = await ReserveFundService(session).close(fund_id, data)
    return ReserveFundResponse.model_validate(fund)


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
