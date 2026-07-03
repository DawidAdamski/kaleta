"""Cashflow chart widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import apply_dark
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register


def _build_cashflow_chart(months: list[MonthCashflow], is_dark: bool) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {
            "data": [t("common.income"), t("common.expense"), t("dashboard.net")],
            "bottom": 0,
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "category", "data": [m.label for m in months]},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "series": [
            {
                "name": t("common.income"),
                "type": "bar",
                "stack": "cashflow",
                "data": [float(m.income) for m in months],
                "itemStyle": {"color": "#4caf50"},
            },
            {
                "name": t("common.expense"),
                "type": "bar",
                "stack": "cashflow",
                "data": [-float(m.expenses) for m in months],
                "itemStyle": {"color": "#ef5350"},
            },
            {
                "name": t("dashboard.net"),
                "type": "line",
                "data": [float(m.net) for m in months],
                "itemStyle": {"color": "#1976d2"},
                "lineStyle": {"width": 2},
                "symbol": "circle",
                "symbolSize": 6,
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
    with section_card(t("dashboard.cashflow_chart"), subtitle=t("dashboard_widgets.cashflow_sub")):
        ui.echart(_build_cashflow_chart(months, is_dark)).classes("w-full h-72")
