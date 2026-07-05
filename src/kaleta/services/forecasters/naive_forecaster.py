# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lightweight balance forecaster — seasonal-naive with quantile confidence band."""

from __future__ import annotations

import datetime
import statistics
from collections import defaultdict

ForecastRow = tuple[datetime.date, float, float, float]

# Z-score for an ~80% two-sided interval (matches Prophet's interval_width=0.80).
_Z_80 = 1.28
# Same-weekday look-back window for seasonal-naive deltas.
_WEEKS_LOOKBACK = 8


class NaiveForecaster:
    """Seasonal-naive projection: repeat each weekday's average daily balance change.

    Confidence bands use the historical spread of same-weekday deltas, widened
    slightly with the square root of forecast horizon (heteroskedastic fan).
    """

    @property
    def model_name(self) -> str:
        return "naive"

    def run(
        self,
        running: dict[datetime.date, float],
        horizon_days: int,
    ) -> list[ForecastRow] | None:
        sorted_days = sorted(running.keys())
        if len(sorted_days) < 14:
            return None

        deltas = _daily_deltas(running, sorted_days)
        if not deltas:
            return None

        weekday_stats = _weekday_delta_stats(deltas, weeks=_WEEKS_LOOKBACK)
        fallback_mean = statistics.mean(deltas.values())
        fallback_spread = _spread(list(deltas.values()), fallback_mean)

        last_date = sorted_days[-1]
        last_balance = running[last_date]

        rows: list[ForecastRow] = []
        for d in sorted_days:
            bal = running[d]
            rows.append((d, bal, bal, bal))

        balance = last_balance
        for step in range(1, horizon_days + 1):
            fd = last_date + datetime.timedelta(days=step)
            wd = fd.weekday()
            mean_delta, spread = weekday_stats.get(wd, (fallback_mean, fallback_spread))
            balance = balance + mean_delta
            margin = _Z_80 * spread * (step**0.5)
            rows.append((fd, balance, balance - margin, balance + margin))

        return rows


def _daily_deltas(
    running: dict[datetime.date, float],
    sorted_days: list[datetime.date],
) -> dict[datetime.date, float]:
    deltas: dict[datetime.date, float] = {}
    for i in range(1, len(sorted_days)):
        prev, cur = sorted_days[i - 1], sorted_days[i]
        deltas[cur] = running[cur] - running[prev]
    return deltas


def _weekday_delta_stats(
    deltas: dict[datetime.date, float],
    *,
    weeks: int,
) -> dict[int, tuple[float, float]]:
    """Map weekday → (mean delta, spread) using the most recent ``weeks`` occurrences."""
    by_weekday: dict[int, list[tuple[datetime.date, float]]] = defaultdict(list)
    for d, delta in deltas.items():
        by_weekday[d.weekday()].append((d, delta))

    stats: dict[int, tuple[float, float]] = {}
    cutoff = max(deltas.keys()) - datetime.timedelta(days=weeks * 7)
    for wd, entries in by_weekday.items():
        recent = [delta for d, delta in entries if d >= cutoff]
        if not recent:
            recent = [delta for _, delta in entries]
        mean = statistics.mean(recent)
        stats[wd] = (mean, _spread(recent, mean))
    return stats


def _spread(values: list[float], mean: float) -> float:
    vals = list(values)
    if len(vals) > 1:
        return statistics.pstdev(vals)
    if vals:
        return max(abs(vals[0]), abs(mean), 1.0) * 0.1
    return 1.0
