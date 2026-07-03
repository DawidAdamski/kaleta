"""Predicted 30-day balance KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.services.forecast_service import ForecastService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "predicted_30d",
    "dashboard_widgets.predicted_30d",
    "insights",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_predicted_30d(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    total = await ReportService(session).total_balance()
    result = await ForecastService(session).forecast_account(account_id=None, horizon_days=30)
    pred = result.predicted_balance_30d
    if pred is None:
        kpi_card(t("dashboard.balance_30"), "—", "insights", "grey-6")
        return
    color = "green-7" if pred >= float(total) else "red-7"
    kpi_card(t("dashboard.balance_30"), fmt_amount(pred), "insights", color)
