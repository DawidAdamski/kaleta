"""Forecast model backends — Prophet (optional) or lightweight naive fallback."""

from __future__ import annotations

import datetime
import importlib.util
import logging
from functools import lru_cache
from typing import Protocol

from kaleta.services.forecasters.naive_forecaster import NaiveForecaster
from kaleta.services.forecasters.prophet_forecaster import ProphetForecaster

log = logging.getLogger(__name__)

ForecastRow = tuple[datetime.date, float, float, float]


class Forecaster(Protocol):
    """Synchronous forecaster — runs in a thread pool via ``run_in_executor``."""

    @property
    def model_name(self) -> str: ...

    def run(
        self,
        running: dict[datetime.date, float],
        horizon_days: int,
    ) -> list[ForecastRow] | None: ...


@lru_cache(maxsize=1)
def _prophet_importable() -> bool:
    return importlib.util.find_spec("prophet") is not None


def is_prophet_available() -> bool:
    """Return True when the optional ``forecast`` extra (Prophet) is installed."""
    return _prophet_importable()


def active_forecaster_model() -> str:
    """Return ``prophet`` or ``naive`` for the backend selected at runtime."""
    return "prophet" if is_prophet_available() else "naive"


def get_forecaster() -> Forecaster:
    """Select Prophet when importable, otherwise the naive fallback."""
    if is_prophet_available():
        return ProphetForecaster()
    log.warning("Prophet not installed — using naive forecast fallback")
    return NaiveForecaster()


__all__ = [
    "Forecaster",
    "NaiveForecaster",
    "ProphetForecaster",
    "active_forecaster_model",
    "get_forecaster",
    "is_prophet_available",
]
