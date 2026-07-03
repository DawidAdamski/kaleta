"""Month expenses KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "month_expenses",
    "dashboard_widgets.month_expenses",
    "trending_down",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_month_expenses(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    _, expenses = await ReportService(session).current_month_summary()
    kpi_card(t("dashboard.month_expenses"), fmt_amount(expenses), "trending_down", "red-7")
