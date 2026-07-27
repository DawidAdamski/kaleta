# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.analysis import NetWorthSnapshotResponse
from kaleta.services.net_worth_service import NetWorthService

router = APIRouter(prefix="/net-worth", tags=["Net worth"])


@router.get("/", response_model=NetWorthSnapshotResponse, summary="Current net worth snapshot")
async def get_net_worth(
    default_currency: str = Query("PLN", min_length=3, max_length=3),
    session: AsyncSession = Depends(get_session),
) -> NetWorthSnapshotResponse:
    summary = await NetWorthService(session).get_summary(default_currency=default_currency)
    return NetWorthSnapshotResponse(
        total_assets=summary.total_assets,
        total_liabilities=summary.total_liabilities,
        net_worth=summary.net_worth,
        default_currency=summary.default_currency,
        prev_month_net_worth=summary.prev_month_net_worth,
        has_unknown_rates=summary.has_unknown_rates,
    )
