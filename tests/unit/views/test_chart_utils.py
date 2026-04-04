"""Unit tests for apply_dark() and related helpers in kaleta.views.chart_utils.

All functions are pure (no DB, no NiceGUI runtime) so plain def tests are used.
"""

from __future__ import annotations

from kaleta.views.chart_utils import apply_dark, axis_style, chart_text_color

DARK_COLOR = "#e0e0e0"
LIGHT_COLOR = "#333333"
DARK_SPLIT = "#444444"
LIGHT_SPLIT = "#e0e0e0"


# ── chart_text_color ───────────────────────────────────────────────────────────


def test_chart_text_color_dark() -> None:
    assert chart_text_color(True) == DARK_COLOR


def test_chart_text_color_light() -> None:
    assert chart_text_color(False) == LIGHT_COLOR


# ── axis_style ────────────────────────────────────────────────────────────────


def test_axis_style_dark_returns_light_text() -> None:
    style = axis_style(True)
    assert style["legend_text"]["color"] == DARK_COLOR
    assert style["axis_label"]["color"] == DARK_COLOR


def test_axis_style_light_returns_dark_text() -> None:
    style = axis_style(False)
    assert style["legend_text"]["color"] == LIGHT_COLOR
    assert style["axis_label"]["color"] == LIGHT_COLOR


def test_axis_style_dark_split_line_color() -> None:
    style = axis_style(True)
    assert style["split_line"]["lineStyle"]["color"] == DARK_SPLIT


def test_axis_style_light_split_line_color() -> None:
    style = axis_style(False)
    assert style["split_line"]["lineStyle"]["color"] == LIGHT_SPLIT


# ── apply_dark — no-op when is_dark=False ─────────────────────────────────────


def test_apply_dark_noop_when_not_dark() -> None:
    opts: dict = {
        "legend": {"data": ["A"]},
        "xAxis": {"type": "value"},
        "yAxis": {"type": "category"},
    }
    original_legend = opts["legend"].copy()
    result = apply_dark(opts, is_dark=False)
    # Returns the same object unchanged
    assert result is opts
    assert result["legend"] == original_legend
    # No textStyle injected
    assert "textStyle" not in result["legend"]


# ── apply_dark — legend text colour in dark mode ──────────────────────────────


def test_apply_dark_sets_legend_text_color() -> None:
    opts: dict = {"legend": {"data": ["Budget", "Actual"]}}
    apply_dark(opts, is_dark=True)
    assert opts["legend"]["textStyle"]["color"] == DARK_COLOR


def test_apply_dark_preserves_existing_legend_keys() -> None:
    opts: dict = {"legend": {"data": ["X"], "bottom": 0}}
    apply_dark(opts, is_dark=True)
    assert opts["legend"]["bottom"] == 0
    assert opts["legend"]["data"] == ["X"]


# ── apply_dark — axis label colour in dark mode ───────────────────────────────


def test_apply_dark_sets_xaxis_label_color() -> None:
    opts: dict = {"xAxis": {"type": "value"}}
    apply_dark(opts, is_dark=True)
    assert opts["xAxis"]["axisLabel"]["color"] == DARK_COLOR


def test_apply_dark_sets_yaxis_label_color() -> None:
    opts: dict = {"yAxis": {"type": "category", "data": ["A", "B"]}}
    apply_dark(opts, is_dark=True)
    assert opts["yAxis"]["axisLabel"]["color"] == DARK_COLOR


def test_apply_dark_sets_xaxis_line_color() -> None:
    opts: dict = {"xAxis": {"type": "value"}}
    apply_dark(opts, is_dark=True)
    assert opts["xAxis"]["axisLine"]["lineStyle"]["color"] == DARK_COLOR


def test_apply_dark_sets_split_line_color() -> None:
    opts: dict = {"xAxis": {"type": "value"}}
    apply_dark(opts, is_dark=True)
    assert opts["xAxis"]["splitLine"]["lineStyle"]["color"] == DARK_SPLIT


# ── apply_dark — axes given as a list ─────────────────────────────────────────


def test_apply_dark_handles_list_of_axes() -> None:
    opts: dict = {"xAxis": [{"type": "value"}, {"type": "value", "name": "secondary"}]}
    apply_dark(opts, is_dark=True)
    for ax in opts["xAxis"]:
        assert ax["axisLabel"]["color"] == DARK_COLOR


# ── apply_dark — missing keys handled gracefully ──────────────────────────────


def test_apply_dark_no_legend_key_no_error() -> None:
    opts: dict = {"xAxis": {"type": "value"}}
    # Must not raise even when 'legend' is absent
    result = apply_dark(opts, is_dark=True)
    assert "legend" not in result


def test_apply_dark_no_axis_keys_no_error() -> None:
    opts: dict = {"legend": {"data": ["A"]}}
    result = apply_dark(opts, is_dark=True)
    assert "xAxis" not in result
    assert "yAxis" not in result


def test_apply_dark_empty_dict_no_error() -> None:
    opts: dict = {}
    result = apply_dark(opts, is_dark=True)
    assert result == {}


def test_apply_dark_returns_same_object() -> None:
    opts: dict = {"legend": {}}
    result = apply_dark(opts, is_dark=True)
    assert result is opts


# ── apply_dark — combined legend + axes (realistic chart options) ─────────────


def test_apply_dark_full_options_dict() -> None:
    opts: dict = {
        "legend": {"data": ["Budget", "Actual"], "bottom": 0},
        "xAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "yAxis": {"type": "category", "data": ["Food", "Rent"], "inverse": True},
    }
    apply_dark(opts, is_dark=True)

    assert opts["legend"]["textStyle"]["color"] == DARK_COLOR
    # Pre-existing formatter must survive
    assert opts["xAxis"]["axisLabel"]["formatter"] == "{value} zł"
    assert opts["xAxis"]["axisLabel"]["color"] == DARK_COLOR
    assert opts["yAxis"]["axisLabel"]["color"] == DARK_COLOR
