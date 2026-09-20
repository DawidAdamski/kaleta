# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared chart helpers — palette and dark-mode overrides for ECharts.

ECharts cannot read CSS custom properties, so the sand tokens declared in
``views/theme.py`` are mirrored here as literals. Keep the two in step: the
hex values below come from the same handoff tables (``docs/design/restyle``).
"""

from __future__ import annotations

from typing import Any

# Series palette — ink, accent, income, expense, neutral bar, confidence band.
# Every ECharts instance draws from this list instead of per-view hexes.
CHART_INK = "#1C1A15"
CHART_ACCENT = "#B4591F"
CHART_INCOME = "#36684D"
CHART_EXPENSE = "#A44631"
CHART_NEUTRAL_BAR = "#8E8676"
CHART_BAND = "#EFCDB2"

CHART_PALETTE = [
    CHART_INK,
    CHART_ACCENT,
    CHART_INCOME,
    CHART_EXPENSE,
    CHART_NEUTRAL_BAR,
    CHART_BAND,
]

# Dark-mode series colours — the warm-dark token row of the same tables.
CHART_INK_DARK = "#F0EBDF"
CHART_ACCENT_DARK = "#E8935B"
CHART_INCOME_DARK = "#6FAF87"
CHART_EXPENSE_DARK = "#DE8672"

CHART_PALETTE_DARK = [
    CHART_INK_DARK,
    CHART_ACCENT_DARK,
    CHART_INCOME_DARK,
    CHART_EXPENSE_DARK,
    CHART_NEUTRAL_BAR,
    CHART_BAND,
]

#: The accent as a *series* line, which the artboards draw a shade lighter
#: than the accent a surface is filled with (`--k-accent-light`): a 2.5px
#: stroke at #B4591F reads as brown on sand, not as the apricot beside it.
#: Dark mode has one apricot for both.
CHART_ACCENT_SERIES = "#DE7B45"

CHART_ACCENT_FILL = "rgba(180, 89, 31, 0.18)"
CHART_ACCENT_FILL_DARK = "rgba(232, 147, 91, 0.18)"

#: Paper, for a symbol drawn *on* a card rather than filled with a series
#: colour — ECharts cannot read `--k-surface`, so it is mirrored here too.
CHART_SURFACE = "#FCFAF6"
CHART_SURFACE_DARK = "#201F1A"

# Axis labels, grid lines — muted / hairline in each mode.
CHART_GRID_DARK = "#322F27"
CHART_GRID_LIGHT = "#E2DBCC"
CHART_TEXT_DARK = "#A8A08D"
CHART_TEXT_LIGHT = "#6B6353"


def chart_text_color(is_dark: bool) -> str:
    return CHART_TEXT_DARK if is_dark else CHART_TEXT_LIGHT


def chart_grid_color(is_dark: bool) -> str:
    return CHART_GRID_DARK if is_dark else CHART_GRID_LIGHT


def chart_palette(is_dark: bool) -> list[str]:
    """Series colours for the active mode, in draw order."""
    return list(CHART_PALETTE_DARK if is_dark else CHART_PALETTE)


def chart_ink_color(is_dark: bool) -> str:
    return CHART_INK_DARK if is_dark else CHART_INK


def chart_income_color(is_dark: bool) -> str:
    return CHART_INCOME_DARK if is_dark else CHART_INCOME


def chart_expense_color(is_dark: bool) -> str:
    return CHART_EXPENSE_DARK if is_dark else CHART_EXPENSE


def chart_accent_color(is_dark: bool) -> str:
    return CHART_ACCENT_DARK if is_dark else CHART_ACCENT


def chart_surface_color(is_dark: bool) -> str:
    return CHART_SURFACE_DARK if is_dark else CHART_SURFACE


def chart_series_accent_color(is_dark: bool) -> str:
    """The accent for a line or a bar, as the artboards draw one."""
    return CHART_ACCENT_DARK if is_dark else CHART_ACCENT_SERIES


def chart_accent_fill(is_dark: bool) -> str:
    """Area-fill tint of the accent — must follow the mode like the line does."""
    return CHART_ACCENT_FILL_DARK if is_dark else CHART_ACCENT_FILL


#: The two faces every artboard sets its axes in — figures in mono, names in
#: the body face, both a size down from the card they sit in (`1c`, `3a`,
#: `3b`). A chart that names its own axis fonts is a chart that will drift.
AXIS_LABEL_MONO = {"fontFamily": "IBM Plex Mono, ui-monospace, monospace", "fontSize": 10.5}
AXIS_LABEL_BODY = {"fontFamily": "Libre Franklin, system-ui, sans-serif", "fontSize": 11.5}


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
    """Inject the sand palette and mode-aware text/grid colours into ECharts options.

    The series palette is seeded with ``setdefault`` so a chart that names its
    own colours (per-series ``itemStyle``) keeps them, while one that names
    none picks up the system palette instead of ECharts' default blue ramp.
    """
    options.setdefault("color", chart_palette(is_dark))
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
