# SPDX-License-Identifier: AGPL-3.0-or-later
"""The forecast line chart, shared by the Forecast page and the simulator.

Extracted from ``views/forecast.py`` so the what-if panel draws the *same*
picture rather than a lookalike: the band, the today marker and the scenario
pins all behave identically because they are the same code. Any divergence
between the two screens would be a bug in one of them.
"""

from __future__ import annotations

import datetime
from typing import Any

from kaleta.i18n import t
from kaleta.services.forecast_service import (
    ForecastResult,
    ScenarioShift,
    point_shifted_by,
)
from kaleta.views.chart_utils import (
    AXIS_LABEL_BODY,
    AXIS_LABEL_MONO,
    AXIS_VALUE_SPACED,
    CHART_BAND,
    CHART_NEUTRAL_BAR,
    apply_dark,
    chart_accent_color,
    chart_accent_fill,
    chart_grid_color,
    chart_ink_color,
    chart_text_color,
)


def forecast_chart(
    result: ForecastResult,
    is_dark: bool = False,
    baseline: ForecastResult | None = None,
    scenarios: list[ScenarioShift] | None = None,
) -> dict[str, Any]:
    """One chart: what happened, what is predicted, and how sure that is.

    The x-axis is ``time``, not ``category``. A category axis spaces points
    evenly whichever dates they carry, so ninety days of history drawn beside
    sixty daily forecast points came out compressed — the past looked like it
    happened faster than the future. A time axis puts every point where its
    date belongs.
    """
    today = datetime.date.today()
    scenarios = scenarios or []

    hist = [[str(p.date), p.value] for p in result.historical]
    fore = [[str(p.date), p.value] for p in result.forecast]
    lower = [[str(p.date), p.lower] for p in result.forecast]
    # The band is drawn by stacking its height on top of its floor, so the
    # floor is the *lower* bound: stacking on the upper one would have put the
    # whole band above the prediction it is supposed to surround.
    band = [[str(p.date), round(p.upper - p.lower, 2)] for p in result.forecast]
    base_fore = [[str(p.date), p.value] for p in baseline.forecast] if baseline else []

    # The prediction starts where the history stops, so the two lines meet
    # instead of leaving a day-wide gap at today.
    if hist and fore:
        fore = [hist[-1], *fore]

    accent = chart_accent_color(is_dark)
    grid_color = chart_grid_color(is_dark)
    # The plan's colours exactly: #EFCDB2 in light, and in dark the accent at
    # 0.18 — which `chart_accent_fill` already carries as an rgba, so neither
    # needs an opacity of its own.
    band_color = chart_accent_fill(is_dark) if is_dark else CHART_BAND

    mark_lines: list[dict[str, Any]] = [
        {
            "xAxis": str(today),
            "name": t("forecast.today"),
            "label": {"formatter": t("forecast.today"), "color": chart_text_color(is_dark)},
        }
    ]
    mark_points: list[dict[str, Any]] = []
    for shift in scenarios:
        mark_lines.append(
            {
                "xAxis": str(shift.date),
                "name": shift.label,
                "label": {"formatter": shift.label, "color": accent},
                "lineStyle": {"color": accent, "type": "dotted"},
            }
        )
        # Exact, because `apply_scenarios` is exact: a pin on a point the
        # shift did not move would say the line bent where it did not.
        pin = point_shifted_by(result, shift.date)
        if pin is not None:
            mark_points.append(
                {"coord": [str(pin.date), pin.value], "name": shift.label, "value": shift.label}
            )

    _opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        # No legend inside the frame: artboard `3a` reads the four keys on
        # the card's title line, where they cost the chart no height and are
        # read before the picture rather than after it.
        "legend": {"show": False},
        # 26 at the top, not 12: the "Today" mark-line writes its label
        # above the frame and a tighter grid clips it.
        "grid": {"left": 8, "right": 16, "top": 26, "bottom": 8, "containLabel": True},
        "xAxis": {"type": "time", "axisLabel": AXIS_LABEL_BODY},
        # The currency is on the card, not on every gridline: eleven "zł"
        # down the left edge say the same thing eleven times.
        "yAxis": {
            "type": "value",
            "axisLabel": {**AXIS_LABEL_MONO, ":formatter": AXIS_VALUE_SPACED},
        },
        "series": [
            {
                "name": t("forecast.lower"),
                "type": "line",
                "data": lower,
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "silent": True,
                "tooltip": {"show": False},
                "z": 1,
            },
            {
                "name": t("forecast.confidence_band"),
                "type": "line",
                "data": band,
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "areaStyle": {"color": band_color},
                # Its value is the band's *height*, not a balance — "200"
                # under a column of zł figures would read as one.
                "tooltip": {"show": False},
                "z": 1,
            },
            {
                "name": t("forecast.actual"),
                "type": "line",
                "data": hist,
                "itemStyle": {"color": chart_ink_color(is_dark)},
                "lineStyle": {"width": 2},
                "showSymbol": False,
                "z": 3,
            },
            {
                "name": t("forecast.predicted"),
                "type": "line",
                "data": fore,
                "itemStyle": {"color": accent},
                "lineStyle": {"width": 2, "type": "dashed"},
                "showSymbol": False,
                "z": 3,
                "markLine": {
                    "symbol": "none",
                    "silent": True,
                    "lineStyle": {"color": grid_color, "type": "dashed"},
                    "data": mark_lines,
                },
                "markPoint": {
                    "symbol": "pin",
                    "symbolSize": 34,
                    "itemStyle": {"color": accent},
                    "label": {"show": False},
                    "data": mark_points,
                },
            },
        ],
    }

    if base_fore:
        _opts["series"].append(
            {
                "name": t("forecast.baseline_reference"),
                "type": "line",
                "data": base_fore,
                "itemStyle": {"color": CHART_NEUTRAL_BAR},
                "lineStyle": {"width": 1, "type": "dotted", "color": CHART_NEUTRAL_BAR},
                "showSymbol": False,
                "z": 2,
            }
        )

    return apply_dark(_opts, is_dark)


__all__ = ["forecast_chart"]
