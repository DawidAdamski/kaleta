# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prophet-based forecaster — lazy-imports the optional dependency."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# Suppress noisy Stan / Prophet output when the extra is installed.
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

ForecastRow = tuple[datetime.date, float, float, float]


class ProphetForecaster:
    """Meta Prophet backend — unchanged behaviour from the original implementation."""

    @property
    def model_name(self) -> str:
        return "prophet"

    def run(
        self,
        running: dict[datetime.date, float],
        horizon_days: int,
    ) -> list[ForecastRow] | None:
        try:
            import pandas as pd  # type: ignore[import-untyped]
            from prophet import Prophet  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            df = pd.DataFrame([{"ds": d, "y": v} for d, v in sorted(running.items())])

            model = Prophet(
                yearly_seasonality=True,
                weekly_seasonality=True,
                daily_seasonality=False,
                interval_width=0.80,
            )
            model.fit(df)

            future = model.make_future_dataframe(periods=horizon_days, freq="D")
            forecast = model.predict(future)

            rows: Sequence[tuple[datetime.date, float, float, float]] = [
                (
                    row["ds"].date(),
                    row["yhat"],
                    row["yhat_lower"],
                    row["yhat_upper"],
                )
                for _, row in forecast.iterrows()
            ]
            return list(rows)
        except Exception:
            return None
