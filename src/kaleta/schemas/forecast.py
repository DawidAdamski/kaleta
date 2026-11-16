# SPDX-License-Identifier: AGPL-3.0-or-later
"""Response schemas for ``/api/v1/forecast``."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel

__all__ = ["ForecastKpisResponse", "ForecastPointResponse", "ForecastResponse"]


class ForecastPointResponse(BaseModel):
    date: datetime.date
    value: Decimal
    lower: Decimal
    upper: Decimal
    #: False for the reconstructed history, true for the forecast after it.
    is_forecast: bool


class ForecastKpisResponse(BaseModel):
    #: The balance on the last history day (``balance_date``), not necessarily today.
    balance_today: Decimal | None
    balance_date: datetime.date | None
    #: The forecast balance on the last forecast day (``horizon_date``).
    predicted: Decimal | None
    change: Decimal | None
    #: Half the prediction interval at the horizon.
    confidence: Decimal | None
    horizon_date: datetime.date | None


class ForecastResponse(BaseModel):
    account_id: int | None
    account_name: str
    horizon_days: int
    preset: str
    #: ``prophet`` or ``naive`` — which model produced the forecast.
    forecaster_model: str
    insufficient_data: bool
    points: list[ForecastPointResponse]
    kpis: ForecastKpisResponse | None
