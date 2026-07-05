# SPDX-License-Identifier: AGPL-3.0-or-later
"""Total balance KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "total_balance",
    "dashboard_widgets.total_balance",
    "account_balance",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_total_balance(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    total = await ReportService(session).total_balance()
    kpi_card(t("dashboard.total_balance"), fmt_amount(total), "account_balance", "blue-7")
