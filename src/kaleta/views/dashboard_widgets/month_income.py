# SPDX-License-Identifier: AGPL-3.0-or-later
"""Month income KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "month_income",
    "dashboard_widgets.month_income",
    "trending_up",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_month_income(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    income, _ = await ReportService(session).current_month_summary()
    kpi_card(t("dashboard.month_income"), fmt_amount(income), "trending_up", "green-7")
