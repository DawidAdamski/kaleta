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
from kaleta.views.chart_utils import apply_dark, chart_text_color


def report_chart_options(
    result: ReportResult,
    chart_type: str,
    is_dark: bool,
) -> dict[str, Any]:
    """Options for one report chart, in the app's own palette.

    Not every chart type: ``bar`` is drawn as rows of HTML (artboard `3e`)
    and ``table`` as a table, so this only ever answers for the three that
    really are charts.
    """
    if chart_type in ("pie", "donut"):
        return _pie_options(result, chart_type, is_dark)
    return _line_options(result, is_dark)


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
