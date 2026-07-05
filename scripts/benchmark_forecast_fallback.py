# SPDX-License-Identifier: AGPL-3.0-or-later
"""Benchmark seasonal-naive vs rolling-30-day-mean on seed-like balance series.

Run:
    uv run python scripts/benchmark_forecast_fallback.py
"""

from __future__ import annotations

import datetime
import math
import os
import random
import statistics
import sys
from pathlib import Path

os.environ.setdefault("KALETA_DEBUG", "true")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kaleta.services.forecasters.naive_forecaster import NaiveForecaster

random.seed(42)

HOLDOUT_DAYS = 30
HISTORY_DAYS = 365
N_SERIES = 5
_Z_80 = 1.28


def _build_seed_like_series(
    *,
    days: int,
    start_balance: float,
    rng: random.Random,
) -> dict[datetime.date, float]:
    """Synthetic balance series with weekly pay-day spikes and monthly bills."""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    balance = start_balance
    running: dict[datetime.date, float] = {}
    for i in range(days):
        d = start + datetime.timedelta(days=i)
        delta = rng.uniform(-80, 40)
        if d.weekday() == 4:  # Friday pay-day uplift
            delta += rng.uniform(800, 1200)
        if d.day in (1, 15):  # rent / utilities
            delta -= rng.uniform(400, 900)
        if d.month in (7, 8):  # summer spend season
            delta -= rng.uniform(0, 60)
        balance += delta
        running[d] = balance
    return running


def _rolling_mean_forecast(
    running: dict[datetime.date, float],
    horizon_days: int,
) -> list[tuple[datetime.date, float, float, float]] | None:
    """Rolling 30-day mean daily delta with linear trend — benchmark candidate."""
    sorted_days = sorted(running.keys())
    if len(sorted_days) < 14:
        return None

    deltas: list[float] = []
    for i in range(1, len(sorted_days)):
        deltas.append(running[sorted_days[i]] - running[sorted_days[i - 1]])

    window = deltas[-30:] if len(deltas) >= 30 else deltas
    mean_delta = statistics.mean(window)
    trend = 0.0
    if len(deltas) >= 14:
        recent = statistics.mean(deltas[-7:])
        prior = statistics.mean(deltas[-14:-7])
        trend = (recent - prior) / 7.0
    spread = statistics.pstdev(window) if len(window) > 1 else max(abs(mean_delta), 1.0) * 0.1

    last_date = sorted_days[-1]
    last_balance = running[last_date]
    rows: list[tuple[datetime.date, float, float, float]] = []
    for d in sorted_days:
        bal = running[d]
        rows.append((d, bal, bal, bal))

    balance = last_balance
    for step in range(1, horizon_days + 1):
        fd = last_date + datetime.timedelta(days=step)
        delta = mean_delta + trend * step
        balance += delta
        margin = _Z_80 * spread * (step**0.5)
        rows.append((fd, balance, balance - margin, balance + margin))
    return rows


def _holdout_errors(
    full: dict[datetime.date, float],
    forecaster_fn,
) -> tuple[float, float]:
    """Return (MAE, RMSE) on the last HOLDOUT_DAYS balance values."""
    sorted_days = sorted(full.keys())
    train_days = sorted_days[:-HOLDOUT_DAYS]
    holdout = sorted_days[-HOLDOUT_DAYS:]

    train_running = {d: full[d] for d in train_days}
    predicted = forecaster_fn(train_running, HOLDOUT_DAYS)
    if predicted is None:
        return float("inf"), float("inf")

    pred_by_date = {d: yhat for d, yhat, _, _ in predicted if d in holdout}
    errors = [pred_by_date[d] - full[d] for d in holdout if d in pred_by_date]
    if not errors:
        return float("inf"), float("inf")

    mae = statistics.mean(abs(e) for e in errors)
    rmse = math.sqrt(statistics.mean(e * e for e in errors))
    return mae, rmse


def main() -> None:
    seasonal = NaiveForecaster()
    seasonal_scores: list[tuple[float, float]] = []
    rolling_scores: list[tuple[float, float]] = []

    for i in range(N_SERIES):
        rng = random.Random(42 + i)
        series = _build_seed_like_series(
            days=HISTORY_DAYS,
            start_balance=rng.uniform(2000, 8000),
            rng=rng,
        )
        seasonal_scores.append(_holdout_errors(series, seasonal.run))
        rolling_scores.append(_holdout_errors(series, _rolling_mean_forecast))

    def _avg(scores: list[tuple[float, float]]) -> tuple[float, float]:
        maes = [s[0] for s in scores if math.isfinite(s[0])]
        rmses = [s[1] for s in scores if math.isfinite(s[1])]
        return statistics.mean(maes), statistics.mean(rmses)

    s_mae, s_rmse = _avg(seasonal_scores)
    r_mae, r_rmse = _avg(rolling_scores)

    print("Forecast fallback benchmark (seed-like synthetic series)")
    print(f"  Holdout: {HOLDOUT_DAYS} days | Series: {N_SERIES} | History: {HISTORY_DAYS} days")
    print(f"  Seasonal-naive (weekly):  MAE={s_mae:,.2f}  RMSE={s_rmse:,.2f}")
    print(f"  Rolling 30-day mean:      MAE={r_mae:,.2f}  RMSE={r_rmse:,.2f}")
    winner = "seasonal-naive" if s_mae <= r_mae else "rolling-30-day-mean"
    print(f"  Winner (lower MAE): {winner}")


if __name__ == "__main__":
    main()
