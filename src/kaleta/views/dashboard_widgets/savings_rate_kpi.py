"""Savings rate KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "savings_rate_kpi",
    "dashboard_widgets.savings_rate_kpi",
    "savings",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_savings_rate_kpi(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    points = await ReportService(session).savings_rate(months=1)
    latest = points[0] if points else None
    rate = latest.rate_pct if latest else None
    value = "—" if rate is None else f"{float(rate):.1f}%"
    color = "green-7" if rate is not None and rate >= 20 else "orange-7"
    kpi_card(t("dashboard_widgets.savings_rate_kpi"), value, "savings", color)
