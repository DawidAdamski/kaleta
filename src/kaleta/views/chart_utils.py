"""Shared chart helpers — dark mode text colour overrides for ECharts."""
from __future__ import annotations


def chart_text_color(is_dark: bool) -> str:
    return "#e0e0e0" if is_dark else "#333333"


def axis_style(is_dark: bool) -> dict:
    """Common axis / legend style overrides for dark mode."""
    color = chart_text_color(is_dark)
    split_color = "#444444" if is_dark else "#e0e0e0"
    return {
        "legend_text": {"color": color},
        "axis_label": {"color": color},
        "split_line": {"lineStyle": {"color": split_color}},
    }


def apply_dark(options: dict, is_dark: bool) -> dict:
    """Inject dark-mode-aware text colours into an ECharts options dict in-place."""
    if not is_dark:
        return options

    color = chart_text_color(is_dark)
    split_color = "#444444"

    # Legend
    if "legend" in options:
        options["legend"].setdefault("textStyle", {})["color"] = color

    # Axes (xAxis / yAxis may be a dict or a list)
    for axis_key in ("xAxis", "yAxis"):
        axes = options.get(axis_key)
        if axes is None:
            continue
        items = axes if isinstance(axes, list) else [axes]
        for ax in items:
            ax.setdefault("axisLabel", {})["color"] = color
            ax.setdefault("axisLine", {}).setdefault("lineStyle", {})["color"] = color
            ax.setdefault("splitLine", {}).setdefault("lineStyle", {})["color"] = split_color

    return options
