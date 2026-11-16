# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/forecast`` — where an account's balance is heading."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.schemas.forecast import ForecastKpisResponse, ForecastPointResponse, ForecastResponse
from kaleta.services.forecast_service import (
    ForecastPreset,
    ForecastService,
    apply_preset,
    forecast_kpis,
)

#: The longest horizon one request may ask for — the scenario wizard's 24 × 30 days.
MAX_FORECAST_HORIZON_DAYS = 720

router = APIRouter(prefix="/forecast", tags=["Forecast"])


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _money_or_none(value: float | None) -> Decimal | None:
    return None if value is None else _money(value)


@router.get(
    "/balance",
    response_model=ForecastResponse,
    summary="Forecast an account's balance",
    description=(
        "The daily balance history of one account (all accounts without `account_id`), "
        "then `horizon_days` forecast points with a lower and upper band, starting the "
        "day after the last transaction. `preset` leans the line toward the lower "
        "(conservative) or upper (optimistic) band. With fewer than 14 days of history "
        "the response has `insufficient_data` true, no points and no kpis. "
        "`forecaster_model` says whether Prophet or the naive fallback ran."
    ),
    responses={404: {"description": "The account does not exist"}},
)
async def forecast_balance(
    account_id: int | None = Query(None, description="Omit for all accounts together"),
    horizon_days: int = Query(60, ge=1, le=MAX_FORECAST_HORIZON_DAYS),
    preset: ForecastPreset = Query(ForecastPreset.BASELINE),
    session: AsyncSession = Depends(get_session),
) -> ForecastResponse:
    raw = await ForecastService(session).forecast_account(account_id, horizon_days)
    result = apply_preset(raw, preset)
    kpis = None
    if not result.insufficient_data:
        k = forecast_kpis(result)
        kpis = ForecastKpisResponse(
            balance_today=_money_or_none(k.balance_today),
            balance_date=k.balance_date,
            predicted=_money_or_none(k.predicted),
            change=_money_or_none(k.change),
            confidence=_money_or_none(k.confidence),
            horizon_date=k.horizon_date,
        )
    return ForecastResponse(
        account_id=account_id,
        account_name=result.account_name,
        horizon_days=horizon_days,
        preset=preset.value,
        forecaster_model=result.forecaster_model,
        insufficient_data=result.insufficient_data,
        points=[
            ForecastPointResponse(
                date=p.date,
                value=_money(p.value),
                lower=_money(p.lower),
                upper=_money(p.upper),
                is_forecast=p.is_forecast,
            )
            for p in result.points
        ],
        kpis=kpis,
    )
