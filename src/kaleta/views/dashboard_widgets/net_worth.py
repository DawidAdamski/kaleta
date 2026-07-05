# SPDX-License-Identifier: AGPL-3.0-or-later
"""Net worth KPI widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.i18n import t
from kaleta.services.net_worth_service import NetWorthService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, kpi_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "net_worth",
    "dashboard_widgets.net_worth",
    "account_balance_wallet",
    (2, 1),
    ((1, 1), (2, 1)),
)
async def render_net_worth(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    summary = await NetWorthService(session).get_summary(history_months=2)
    kpi_card(
        t("dashboard_widgets.net_worth"),
        fmt_amount(summary.net_worth),
        "account_balance_wallet",
        "deep-purple-7",
    )
