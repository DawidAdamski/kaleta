# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.reserve_fund import ReserveFundResponse
from kaleta.services.reserve_fund_service import ReserveFundService

router = APIRouter(prefix="/reserve-funds", tags=["Reserve funds"])


@router.get("/", response_model=list[ReserveFundResponse], summary="List reserve funds")
async def list_reserve_funds(
    include_archived: bool = Query(False, description="Include archived funds"),
    session: AsyncSession = Depends(get_session),
) -> list[ReserveFundResponse]:
    return await ReserveFundService(session).list(  # type: ignore[return-value]
        include_archived=include_archived
    )
