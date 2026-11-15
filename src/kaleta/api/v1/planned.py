# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/planned-transactions`` — scheduled and recurring transactions."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.schemas.planned_transaction import (
    PlannedOccurrenceResponse,
    PlannedTransactionCreate,
    PlannedTransactionResponse,
    PlannedTransactionUpdate,
)
from kaleta.services.planned_transaction_service import PlannedTransactionService

# The longest window one occurrences request may ask for.
MAX_OCCURRENCE_SPAN_DAYS = 366

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Planned transaction not found"}}
_422: dict[int | str, dict[str, Any]] = {
    422: {
        "description": (
            "Invalid body, an account, category or payee that does not exist, "
            "or a required field set to null"
        )
    }
}

router = APIRouter(prefix="/planned-transactions", tags=["Planned transactions"])


def _found(pt: PlannedTransaction | None, pt_id: int) -> PlannedTransactionResponse:
    if pt is None:
        raise NotFoundError(f"Planned transaction {pt_id} not found")
    return PlannedTransactionResponse.model_validate(pt)


@router.get(
    "/",
    response_model=list[PlannedTransactionResponse],
    summary="List planned transactions",
    description="Every plan by start date, then name; `active` keeps only active or paused ones.",
)
async def list_planned(
    active: bool | None = Query(None, description="Only active (true) or paused (false) plans"),
    session: AsyncSession = Depends(get_session),
) -> list[PlannedTransactionResponse]:
    plans = await PlannedTransactionService(session).list(active=active)
    return [PlannedTransactionResponse.model_validate(pt) for pt in plans]


@router.post(
    "/",
    response_model=PlannedTransactionResponse,
    status_code=201,
    summary="Create a planned transaction",
    description=(
        "Creates a plan. `target_account_id` makes it a transfer between two of your "
        "own accounts: the money leaves `account_id` and arrives on the target."
    ),
    responses=_422,
)
async def create_planned(
    data: PlannedTransactionCreate,
    session: AsyncSession = Depends(get_session),
) -> PlannedTransactionResponse:
    pt = await PlannedTransactionService(session).create(data)
    return PlannedTransactionResponse.model_validate(pt)


@router.get(
    "/{pt_id}",
    response_model=PlannedTransactionResponse,
    summary="Get a planned transaction",
    responses=_404,
)
async def get_planned(
    pt_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlannedTransactionResponse:
    return _found(await PlannedTransactionService(session).get(pt_id), pt_id)


@router.put(
    "/{pt_id}",
    response_model=PlannedTransactionResponse,
    summary="Update a planned transaction",
    description="Partially updates the plan. Only fields in the body are changed.",
    responses={**_404, **_422},
)
async def update_planned(
    pt_id: int,
    data: PlannedTransactionUpdate,
    session: AsyncSession = Depends(get_session),
) -> PlannedTransactionResponse:
    return _found(await PlannedTransactionService(session).update(pt_id, data), pt_id)


@router.delete(
    "/{pt_id}",
    status_code=204,
    summary="Delete a planned transaction",
    description="Deletes the plan. Transactions already posted from it stay.",
    responses=_404,
)
async def delete_planned(
    pt_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await PlannedTransactionService(session).delete(pt_id):
        raise NotFoundError(f"Planned transaction {pt_id} not found")


@router.post(
    "/{pt_id}/toggle-active",
    response_model=PlannedTransactionResponse,
    summary="Pause or resume a planned transaction",
    description="Flips `is_active`. A paused plan is left out of the Payment Calendar.",
    responses=_404,
)
async def toggle_planned(
    pt_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlannedTransactionResponse:
    return _found(await PlannedTransactionService(session).toggle_active(pt_id), pt_id)


@router.get(
    "/{pt_id}/occurrences",
    response_model=list[PlannedOccurrenceResponse],
    summary="List a planned transaction's occurrences",
    description=(
        "The dates the plan falls on between `start` and `end`, both inclusive, with "
        "the amount of each. A paused plan still lists its schedule. The window may "
        f"span at most {MAX_OCCURRENCE_SPAN_DAYS} days."
    ),
    responses={**_404, 422: {"description": "`end` before `start`, or a window too long"}},
)
async def list_planned_occurrences(
    pt_id: int,
    start: datetime.date,
    end: datetime.date,
    session: AsyncSession = Depends(get_session),
) -> list[PlannedOccurrenceResponse]:
    if end < start:
        raise ValidationError("end must not be before start.")
    if (end - start).days > MAX_OCCURRENCE_SPAN_DAYS:
        raise ValidationError(f"The window may span at most {MAX_OCCURRENCE_SPAN_DAYS} days.")
    service = PlannedTransactionService(session)
    if await service.get(pt_id) is None:
        raise NotFoundError(f"Planned transaction {pt_id} not found")
    occurrences = await service.get_occurrences(start, end, active_only=False, planned_id=pt_id)
    return [PlannedOccurrenceResponse.model_validate(o) for o in occurrences]
