# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared chart helpers — palette and dark-mode overrides for ECharts."""

from __future__ import annotations

from typing import Any

# Mockup-aligned series palette (teal brand + semantic income/expense).
CHART_TEAL = "#14b8a6"
CHART_TEAL_FILL = "rgba(20, 184, 166, 0.18)"
CHART_INCOME = "#22c55e"
CHART_EXPENSE = "#ef4444"
CHART_NET_LINE = "#14b8a6"
CHART_GRID_DARK = "#1e293b"
CHART_GRID_LIGHT = "#e2e8f0"
CHART_TEXT_DARK = "#94a3b8"
CHART_TEXT_LIGHT = "#64748b"


def chart_text_color(is_dark: bool) -> str:
    return CHART_TEXT_DARK if is_dark else CHART_TEXT_LIGHT


def chart_grid_color(is_dark: bool) -> str:
    return CHART_GRID_DARK if is_dark else CHART_GRID_LIGHT


def axis_style(is_dark: bool) -> dict[str, dict[str, Any]]:
    """Common axis / legend style overrides."""
    color = chart_text_color(is_dark)
    split_color = chart_grid_color(is_dark)
    return {
        "legend_text": {"color": color},
        "axis_label": {"color": color},
        "split_line": {"lineStyle": {"color": split_color}},
    }


def apply_dark(options: dict[str, Any], is_dark: bool) -> dict[str, Any]:
    """Inject dark-mode-aware text and grid colours into an ECharts options dict."""
    color = chart_text_color(is_dark)
    split_color = chart_grid_color(is_dark)

    if "legend" in options:
        options["legend"].setdefault("textStyle", {})["color"] = color

    for axis_key in ("xAxis", "yAxis"):
        axes = options.get(axis_key)
        if axes is None:
            continue
        items = axes if isinstance(axes, list) else [axes]
        for ax in items:
            ax.setdefault("axisLabel", {})["color"] = color
            ax.setdefault("axisLine", {}).setdefault("lineStyle", {})["color"] = split_color
            ax.setdefault("splitLine", {}).setdefault("lineStyle", {})["color"] = split_color

    return options
