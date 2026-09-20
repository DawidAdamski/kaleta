# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cashflow chart widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import (
    apply_dark,
    chart_expense_color,
    chart_income_color,
    chart_series_accent_color,
    chart_surface_color,
)
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import CARD_SUBTITLE, CARD_TITLE, DASH_CARD, LEGEND_DOT, LEGEND_LINE

#: Bar width as a share of the category band — artboard `1c` draws a 50px
#: bar on a 182px step. A share rather than a pixel count: the same card is
#: 968px wide on a desktop and 350px on a phone.
_BAR_WIDTH = "27%"

#: The two faces `1c` sets its axes in — figures in mono, month names in the
#: body face, both a size down from the card.
_Y_LABEL = {"fontFamily": "IBM Plex Mono, ui-monospace, monospace", "fontSize": 10.5}
_X_LABEL = {"fontFamily": "Libre Franklin, system-ui, sans-serif", "fontSize": 11.5}


def _month_label(month: MonthCashflow) -> str:
    """ "Jul" — the axis label artboard `1c` draws, not the ``2026-07`` key.

    ``MonthCashflow.label`` is an identifier: sortable, unambiguous, and four
    characters of noise repeated six times under a chart whose title already
    says which six months these are.
    """
    return t(f"common.month_short_{month.month}")


def _build_cashflow_chart(months: list[MonthCashflow], is_dark: bool) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        # No ECharts legend: artboard `1c` puts the three keys on the card's
        # title line, which is outside the chart's box — ``_legend`` draws
        # them there, in the same swatches.
        "grid": {"left": "3%", "right": "4%", "top": 12, "bottom": 8, "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": [_month_label(m) for m in months],
            "axisLabel": dict(_X_LABEL),
            # The artboard draws gridlines and a zero rule, and no axis line
            # or ticks under the month names.
            "axisLine": {"show": False},
            "axisTick": {"show": False},
        },
        # No "zł" suffix: the artboard's axis is bare figures, and the card
        # is already a card about money.
        "yAxis": {
            "type": "value",
            "axisLabel": dict(_Y_LABEL),
            "axisLine": {"show": False},
        },
        "series": [
            {
                "name": t("common.income"),
                "type": "bar",
                "stack": "cashflow",
                # 50px on a 182px step is what `1c` draws: a bar narrower
                # than the space beside it. ECharts' own default leaves a
                # 20% category gap, which at six months is a wall.
                "barWidth": _BAR_WIDTH,
                "data": [float(m.income) for m in months],
                "itemStyle": {"color": chart_income_color(is_dark), "borderRadius": 3},
            },
            {
                "name": t("common.expense"),
                "type": "bar",
                "stack": "cashflow",
                "barWidth": _BAR_WIDTH,
                "data": [-float(m.expenses) for m in months],
                "itemStyle": {"color": chart_expense_color(is_dark), "borderRadius": 3},
            },
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
            },
        ],
    }
    return apply_dark(opts, is_dark)


@register(
    "cashflow_chart",
    "dashboard_widgets.cashflow_chart",
    "bar_chart",
    (4, 2),
    ((2, 2), (4, 2), (4, 3)),
)
async def render_cashflow_chart(session: AsyncSession, is_dark: bool) -> None:
    months = await ReportService(session).cashflow_last_n_months(6)
    with ui.card().classes(DASH_CARD):
        with ui.row().classes("w-full items-baseline justify-between gap-4 mb-[18px]"):
            ui.label(t("dashboard.cashflow_chart")).classes(CARD_TITLE)
            _legend(is_dark)
        ui.echart(_build_cashflow_chart(months, is_dark)).classes("w-full h-60")


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
