# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from kaleta.services.subscription_service import SubscriptionService

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Subscription not found"}}
_422: dict[int | str, dict[str, Any]] = {
    422: {
        "description": (
            "Invalid body, a category outside the Subscriptions tree (ADR-028), "
            "or a payee that does not exist"
        )
    }
}

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


def _found(sub: Subscription | None) -> SubscriptionResponse:
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return SubscriptionResponse.model_validate(sub)


@router.get(
    "/",
    response_model=list[SubscriptionResponse],
    summary="List subscriptions",
    description="All subscriptions by name; `status` keeps only active, muted or cancelled ones.",
)
async def list_subscriptions(
    status: SubscriptionStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionResponse]:
    subscriptions = await SubscriptionService(session).list(status=status)
    return [SubscriptionResponse.model_validate(sub) for sub in subscriptions]


@router.post(
    "/",
    response_model=SubscriptionResponse,
    status_code=201,
    summary="Create a subscription",
    description=(
        "Creates an active subscription. `category_id`, when given, must be the "
        "Subscriptions root or one of its direct children (ADR-028). Without "
        "`next_expected_at` the next charge is projected from `first_seen_at` and "
        "`cadence_days`."
    ),
    responses=_422,
)
async def create_subscription(
    data: SubscriptionCreate,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    return SubscriptionResponse.model_validate(await SubscriptionService(session).create(data))


@router.get(
    "/{sub_id}",
    response_model=SubscriptionResponse,
    summary="Get a subscription",
    responses=_404,
)
async def get_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    return _found(await SubscriptionService(session).get(sub_id))


@router.put(
    "/{sub_id}",
    response_model=SubscriptionResponse,
    summary="Update a subscription",
    description="Partially updates a subscription. Only fields in the body are changed.",
    responses={**_404, **_422},
)
async def update_subscription(
    sub_id: int,
    data: SubscriptionUpdate,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    return _found(await SubscriptionService(session).update(sub_id, data))


@router.delete(
    "/{sub_id}",
    status_code=204,
    summary="Delete a subscription",
    responses=_404,
)
async def delete_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await SubscriptionService(session).delete(sub_id):
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.post(
    "/{sub_id}/cancel",
    response_model=SubscriptionResponse,
    summary="Cancel a subscription",
    description=(
        "Cancels as of `effective_on` (default: today). A future date only schedules "
        "the cancellation: the subscription stays active, with `cancelled_at` set, "
        "until that day."
    ),
    responses=_404,
)
async def cancel_subscription(
    sub_id: int,
    effective_on: datetime.date | None = None,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    return _found(await SubscriptionService(session).cancel(sub_id, effective_on=effective_on))


@router.post(
    "/{sub_id}/reactivate",
    response_model=SubscriptionResponse,
    summary="Reactivate a subscription",
    description="Back to active: clears `muted_until` and `cancelled_at`.",
    responses=_404,
)
async def reactivate_subscription(
    sub_id: int,
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    return _found(await SubscriptionService(session).reactivate(sub_id))
