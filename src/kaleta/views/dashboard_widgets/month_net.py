# SPDX-License-Identifier: AGPL-3.0-or-later
"""Month net KPI widget."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "month_net",
    "dashboard_widgets.month_net",
    "swap_vert",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_month_net(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    svc = ReportService(session)
    income, expenses = await svc.current_month_summary()
    net = income - expenses
    delta = await svc.month_net_delta()
    color_cls = "text-green-700" if net >= 0 else "text-red-700"
    kpi_card(
        t("dashboard.month_net"),
        fmt_amount(net),
        "swap_vert",
        "orange-7",
        extra_cls=color_cls,
        delta=delta,
        hide_trend=net == Decimal("0"),
    )
