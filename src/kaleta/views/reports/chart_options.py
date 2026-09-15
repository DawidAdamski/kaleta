# SPDX-License-Identifier: AGPL-3.0-or-later
"""ECharts options for the report builder's chart (artboard 3e).

These used to live in ``saved_report_service`` and drew in ECharts' default
blue against grey axes — the one chart in the app that had never met the
palette. A chart option dict is presentation, not business logic, so it
belongs on this side of the service boundary where the tokens are.
"""

from __future__ import annotations

from typing import Any

from kaleta.services.saved_report_service import ReportResult
from kaleta.views.chart_utils import apply_dark, chart_ink_color, chart_palette, chart_text_color
from kaleta.views.reports.sentence import share_percents

#: Bars run left to right, so a category's name is read as a word and not as
#: a rotated label — which is what the vertical bars needed at seven items.
_BAR_LABEL_FMT = "{c}"


def report_chart_options(
    result: ReportResult,
    chart_type: str,
    is_dark: bool,
) -> dict[str, Any]:
    """Options for one report chart, in the app's own palette."""
    if chart_type in ("pie", "donut"):
        return _pie_options(result, chart_type, is_dark)
    if chart_type == "line":
        return _line_options(result, is_dark)
    return _bar_options(result, is_dark)


def _pie_options(result: ReportResult, chart_type: str, is_dark: bool) -> dict[str, Any]:
    radius = ["42%", "70%"] if chart_type == "donut" else "66%"
    options: dict[str, Any] = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left", "type": "scroll"},
        "series": [
            {
                "type": "pie",
                "radius": radius,
                "data": [
                    {"name": label, "value": value}
                    for label, value in zip(result.labels, result.values, strict=False)
                ],
                "label": {"color": chart_text_color(is_dark)},
            }
        ],
    }
    return apply_dark(options, is_dark)


def _line_options(result: ReportResult, is_dark: bool) -> dict[str, Any]:
    options: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "grid": {"containLabel": True, "left": "3%", "right": "6%", "bottom": "8%", "top": "8%"},
        "xAxis": {
            "type": "category",
            "data": result.labels,
            "axisLabel": {"rotate": 30 if len(result.labels) > 6 else 0},
        },
        "yAxis": {"type": "value"},
        "series": [
            {
                "type": "line",
                "data": result.values,
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 5,
            }
        ],
    }
    return apply_dark(options, is_dark)


def _bar_options(result: ReportResult, is_dark: bool) -> dict[str, Any]:
    """Horizontal bars, each labelled with its value and its share.

    Horizontal because the dimension is a list of names: vertical bars had to
    rotate them 30° as soon as there were more than six, and a rotated name is
    slower to read than the number beside it.
    """
    shares = share_percents(result.values)
    # ECharts draws a horizontal category axis bottom-up, so the biggest bar
    # ends up at the foot of the chart unless both the data and the axis are
    # reversed — the result reads top-down, largest first, like the table.
    labels = list(reversed(result.labels))
    data = [
        {"value": value, "share": share}
        for value, share in reversed(list(zip(result.values, shares, strict=False)))
    ]
    options: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"containLabel": True, "left": "2%", "right": "12%", "top": "2%", "bottom": "2%"},
        "xAxis": {"type": "value", "splitLine": {"show": True}},
        "yAxis": {"type": "category", "data": labels, "axisTick": {"show": False}},
        "series": [
            {
                "type": "bar",
                "data": data,
                "barMaxWidth": 22,
                "itemStyle": {"color": chart_palette(is_dark)[1], "borderRadius": [0, 3, 3, 0]},
                "label": {
                    "show": True,
                    "position": "right",
                    "color": chart_ink_color(is_dark),
                    "fontSize": 11,
                    # `{c}` on an object datum prints the whole object, so the
                    # value and the share are addressed by name instead.
                    "formatter": "{@value} · {@share}%",
                },
            }
        ],
    }
    return apply_dark(options, is_dark)
