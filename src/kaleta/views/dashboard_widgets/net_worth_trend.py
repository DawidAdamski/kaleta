# SPDX-License-Identifier: AGPL-3.0-or-later
"""Net worth trend chart widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.net_worth_service import NetWorthService
from kaleta.views.chart_utils import CHART_TEAL, CHART_TEAL_FILL, apply_dark
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED


@register(
    "net_worth_trend",
    "dashboard_widgets.net_worth_trend",
    "trending_up",
    (4, 2),
    ((2, 2), (4, 2), (4, 3)),
)
async def render_net_worth_trend(session: AsyncSession, is_dark: bool) -> None:
    summary = await NetWorthService(session).get_summary(history_months=12)
    history = summary.history
    with section_card(
        t("dashboard_widgets.net_worth_trend"),
        subtitle=t("dashboard_widgets.net_worth_trend_sub"),
    ):
        if not history:
            ui.label(t("dashboard_widgets.no_history")).classes(BODY_MUTED)
            return
        labels = [f"{h.year}-{h.month:02d}" for h in history]
        net_values = [float(h.net_worth) for h in history]
        opts: dict[str, Any] = {
            "tooltip": {"trigger": "axis"},
            "grid": {
                "left": "3%",
                "right": "4%",
                "bottom": "8%",
                "containLabel": True,
            },
            "xAxis": {"type": "category", "data": labels},
            "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
            "series": [
                {
                    "name": t("dashboard_widgets.net_worth"),
                    "type": "line",
                    "data": net_values,
                    "smooth": True,
                    "areaStyle": {"color": CHART_TEAL_FILL},
                    "itemStyle": {"color": CHART_TEAL},
                    "lineStyle": {"width": 2, "color": CHART_TEAL},
                    "symbol": "circle",
                    "symbolSize": 5,
                }
            ],
        }
        ui.echart(apply_dark(opts, is_dark)).classes("w-full h-64")
