"""Savings rate trend chart widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "savings_rate_trend",
    "dashboard_widgets.savings_rate_trend",
    "show_chart",
    (4, 2),
    ((2, 2), (4, 2), (4, 3)),
)
async def render_savings_rate_trend(session: AsyncSession, is_dark: bool) -> None:
    points = await ReportService(session).savings_rate(months=6)
    labels = [p.label for p in points]
    rates = [float(p.rate_pct) if p.rate_pct is not None else None for p in points]
    opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "4%", "bottom": "8%", "containLabel": True},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
        "series": [
            {
                "name": t("dashboard_widgets.savings_rate_trend"),
                "type": "line",
                "data": rates,
                "smooth": True,
                "itemStyle": {"color": "#26a69a"},
                "areaStyle": {"color": "#26a69a", "opacity": 0.15},
            }
        ],
    }
    with section_card(
        t("dashboard_widgets.savings_rate_trend"),
        subtitle=t("dashboard_widgets.savings_rate_sub"),
    ):
        ui.echart(apply_dark(opts, is_dark)).classes("w-full h-56")
