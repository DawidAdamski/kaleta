# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cashflow chart widget."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import (
    AXIS_LABEL_BODY,
    AXIS_LABEL_MONO,
    apply_dark,
    chart_expense_color,
    chart_grid_color,
    chart_income_color,
    chart_ink_color,
    chart_series_accent_color,
    chart_surface_color,
)
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import CARD_SUBTITLE, CARD_TITLE, DASH_CARD, LEGEND_DOT, LEGEND_LINE

#: Bar width as a share of the category band — artboard `1c` draws a 50px
#: bar on a 182px step. A share rather than a pixel count: the same card is
#: 968px wide on a desktop and 350px on a phone.
_BAR_WIDTH = "27%"

#: The same measurement off artboard `1f`: a 26px bar on a 56px step. Wider
#: than `1c`'s share because six months on a 350px sketch are already close
#: together, and a 27% bar there is a hairline.
_BAR_WIDTH_NARROW = "46%"

#: The two faces `1c` sets its axes in. They are every artboard's, so they
#: live in `chart_utils` and this card only names them.
_Y_LABEL = AXIS_LABEL_MONO
_X_LABEL = AXIS_LABEL_BODY


def _month_label(month: MonthCashflow) -> str:
    """ "Jul" — the axis label artboard `1c` draws, not the ``2026-07`` key.

    ``MonthCashflow.label`` is an identifier: sortable, unambiguous, and four
    characters of noise repeated six times under a chart whose title already
    says which six months these are.
    """
    return t(f"common.month_short_{month.month}")


def _month_axis_labels(months: list[MonthCashflow], is_dark: bool) -> dict[str, Any]:
    """X-axis labels with the month you are in set in ink, as `1f` draws them.

    The artboard's six letters are five muted and one ``#1C1A15``/600 — the
    only thing on that sketch saying which bar is the month in progress, and
    on a phone the chart has no title beside it to say so instead. ECharts
    styles one label of a category axis through rich text, so the formatter
    tags the last one and ``rich`` carries the weight. The colour is a hex,
    not ``var(--k-ink)``: this is drawn on a canvas, where a CSS variable is
    a string nothing resolves.
    """
    # `json.dumps`, not an f-string quote: a month name is a translation, and
    # the one that eventually carries an apostrophe would otherwise end the
    # JavaScript string literal in the middle of the axis.
    last = json.dumps(_month_label(months[-1]) if months else "")
    return {
        **_X_LABEL,
        # Every month named. Left to itself ECharts thins a crowded axis out,
        # and on a 350px sketch that is six bars under three labels: the
        # reader has to count to find out which bar is the month in progress.
        "interval": 0,
        ":formatter": f"value => value === {last} ? '{{cur|' + value + '}}' : value",
        "rich": {"cur": {**_X_LABEL, "fontWeight": 600, "color": chart_ink_color(is_dark)}},
    }


def _build_cashflow_chart(
    months: list[MonthCashflow], is_dark: bool, *, narrow: bool = False
) -> dict[str, Any]:
    """The six-month bars. *narrow* is artboard `1f`'s sketch of the same data.

    `1f` gives the Month band 120px of chart with month letters under it and
    nothing else: no y-axis figures (they would cost 40px of a 350px content
    width to repeat the In/Out figures standing above the chart), and no
    gridlines behind bars that are read against each other rather than off a
    scale.
    """
    bar_width = _BAR_WIDTH_NARROW if narrow else _BAR_WIDTH
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        # No ECharts legend: artboard `1c` puts the three keys on the card's
        # title line, which is outside the chart's box — ``_legend`` draws
        # them there, in the same swatches.
        "grid": (
            {"left": 0, "right": 0, "top": 4, "bottom": 0, "containLabel": True}
            if narrow
            else {"left": "3%", "right": "4%", "top": 12, "bottom": 8, "containLabel": True}
        ),
        "xAxis": {
            "type": "category",
            "data": [_month_label(m) for m in months],
            "axisLabel": _month_axis_labels(months, is_dark) if narrow else dict(_X_LABEL),
            # The artboard draws gridlines and a zero rule, and no axis line
            # or ticks under the month names.
            "axisLine": {"show": False},
            "axisTick": {"show": False},
        },
        # No "zł" suffix: the artboard's axis is bare figures, and the card
        # is already a card about money.
        "yAxis": {
            "type": "value",
            "axisLabel": {"show": False} if narrow else dict(_Y_LABEL),
            "axisLine": {"show": False},
            "splitLine": {"show": not narrow},
        },
        "series": [
            {
                "name": t("common.income"),
                "type": "bar",
                "stack": "cashflow",
                # 50px on a 182px step is what `1c` draws: a bar narrower
                # than the space beside it. ECharts' own default leaves a
                # 20% category gap, which at six months is a wall.
                "barWidth": bar_width,
                "data": [float(m.income) for m in months],
                "itemStyle": {"color": chart_income_color(is_dark), "borderRadius": 3},
            },
            {
                "name": t("common.expense"),
                "type": "bar",
                "stack": "cashflow",
                "barWidth": bar_width,
                "data": [-float(m.expenses) for m in months],
                "itemStyle": {"color": chart_expense_color(is_dark), "borderRadius": 3},
                # The one rule `1f` draws: what came in above it, what went
                # out below. With the y-axis figures gone it is the only
                # thing saying which way is which, so the sketch cannot lose
                # it as well. A `markLine` and not `xAxis.axisLine`: an axis
                # line on zero takes the month names up there with it.
                **(
                    {
                        "markLine": {
                            "silent": True,
                            "symbol": "none",
                            "label": {"show": False},
                            "lineStyle": {"type": "solid", "color": chart_grid_color(is_dark)},
                            "data": [{"yAxis": 0}],
                        }
                    }
                    if narrow
                    else {}
                ),
            },
        ],
    }
    if not narrow:
        # `1f` draws bars and nothing else. A line has to be read off a scale,
        # and the scale is the first thing 120px of chart gives up — so on a
        # phone the net is the figure standing above the chart, not a series
        # crossing it.
        opts["series"].append(
            {
                "name": t("dashboard.net"),
                "type": "line",
                "data": [float(m.net) for m in months],
                # Paper-filled discs on an accent stroke, as the artboard
                # draws them — a filled dot at this size reads as a bar.
                "itemStyle": {
                    "color": chart_surface_color(is_dark),
                    "borderColor": chart_series_accent_color(is_dark),
                    "borderWidth": 2.5,
                },
                "lineStyle": {"width": 2.5, "color": chart_series_accent_color(is_dark)},
                "symbol": "circle",
                "symbolSize": 9,
            }
        )
    return apply_dark(opts, is_dark)


@register(
    "cashflow_chart",
    "dashboard_widgets.cashflow_chart",
    "bar_chart",
    (4, 2),
    ((2, 2), (4, 2), (4, 3)),
)
async def render_cashflow_chart(session: AsyncSession, ctx: RenderContext) -> None:
    months = await ReportService(session).cashflow_last_n_months(6)
    if ctx.narrow:
        # On the ground, under the band's own heading: artboard `1f` draws the
        # Month band as bare type and a sketch, and a card here would be a
        # second box saying "this month" under the one that already does.
        ui.echart(_build_cashflow_chart(months, ctx.is_dark, narrow=True)).classes(
            "w-full h-[120px]"
        )
        return
    with ui.card().classes(DASH_CARD):
        with ui.row().classes("w-full items-baseline justify-between gap-4 mb-[18px]"):
            ui.label(t("dashboard.cashflow_chart")).classes(CARD_TITLE)
            _legend(ctx.is_dark)
        ui.echart(_build_cashflow_chart(months, ctx.is_dark)).classes("w-full h-60")


def _legend(is_dark: bool) -> None:
    """The three keys on the title line, as artboard `1c` draws them.

    Two square swatches and a rule: the net is a line on the chart, so its
    key is a line here and not a third block.
    """
    with ui.row().classes(f"{CARD_SUBTITLE} items-center gap-4 no-wrap"):
        for label, colour in (
            (t("common.income"), chart_income_color(is_dark)),
            (t("common.expense"), chart_expense_color(is_dark)),
        ):
            with ui.row().classes("items-center gap-1.5 no-wrap"):
                ui.element("span").classes(LEGEND_DOT).style(f"background:{colour}")
                ui.label(label)
        with ui.row().classes("items-center gap-1.5 no-wrap"):
            ui.element("span").classes(LEGEND_LINE).style(
                f"background:{chart_series_accent_color(is_dark)}"
            )
            ui.label(t("dashboard.net"))
