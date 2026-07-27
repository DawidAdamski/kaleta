# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.subscription import SubscriptionResponse
from kaleta.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/", response_model=list[SubscriptionResponse], summary="List subscriptions")
async def list_subscriptions(
    session: AsyncSession = Depends(get_session),
) -> list[SubscriptionResponse]:
    return await SubscriptionService(session).list()  # type: ignore[return-value]
