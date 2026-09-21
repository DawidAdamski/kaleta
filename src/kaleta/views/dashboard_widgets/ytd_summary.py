# SPDX-License-Identifier: AGPL-3.0-or-later
"""Year-to-date summary widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, mini_stat, section_card
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import AMOUNT_EXPENSE, AMOUNT_INCOME, INK


@register(
    "ytd_summary",
    "dashboard_widgets.ytd_summary",
    "calendar_today",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_ytd_summary(session: AsyncSession, ctx: RenderContext) -> None:  # noqa: ARG001
    rep = await ReportService(session).ytd_summary()
    with (
        section_card(
            t("dashboard_widgets.ytd_summary"),
            subtitle=t("dashboard_widgets.ytd_summary_sub"),
        ),
        ui.row().classes("w-full gap-4 flex-wrap mt-1"),
    ):
        mini_stat(t("reports_lib.ytd_income"), fmt_amount(rep.income), AMOUNT_INCOME)
        mini_stat(t("reports_lib.ytd_expenses"), fmt_amount(rep.expenses), AMOUNT_EXPENSE)
        mini_stat(t("reports_lib.ytd_net"), fmt_amount(rep.net), INK)
        rate = rep.savings_rate_pct
        rate_txt = "—" if rate is None else f"{float(rate):.1f}%"
        mini_stat(t("reports_lib.savings_rate"), rate_txt, INK)
