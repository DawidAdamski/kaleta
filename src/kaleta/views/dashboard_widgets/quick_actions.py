# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quick actions widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.dashboard_widgets.helpers import quick_btn, section_card
from kaleta.views.dashboard_widgets.registry import register


@register(
    "quick_actions",
    "dashboard_widgets.quick_actions",
    "bolt",
    (4, 1),
    ((4, 1), (4, 2)),
)
async def render_quick_actions(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    with (
        section_card(
            t("dashboard_widgets.quick_actions"),
            subtitle=t("dashboard_widgets.quick_actions_sub"),
        ),
        ui.row().classes("w-full gap-2 flex-wrap"),
    ):
        quick_btn("add", t("dashboard_widgets.qa_add_tx"), "/transactions")
        quick_btn("insights", t("dashboard_widgets.qa_forecast"), "/forecast")
        quick_btn("assessment", t("dashboard_widgets.qa_reports"), "/reports")
        quick_btn(
            "account_balance_wallet",
            t("dashboard_widgets.qa_net_worth"),
            "/net-worth",
        )
        quick_btn("rule", t("dashboard_widgets.qa_budgets"), "/budgets")
        quick_btn("upload_file", t("dashboard_widgets.qa_import"), "/import")
