"""Budget variance month widget."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.helpers import fmt_amount, section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED


@register(
    "budget_variance_month",
    "dashboard_widgets.budget_variance_month",
    "rule",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_budget_variance_month(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    today = datetime.date.today()
    rep = await ReportService(session).budget_variance(today.year, today.month)
    with section_card(
        t("dashboard_widgets.budget_variance_month"),
        subtitle=t("dashboard_widgets.budget_variance_sub"),
    ):
        if not rep.rows:
            ui.label(t("dashboard_widgets.no_budgets")).classes(BODY_MUTED)
            return
        over = rep.over_budget_rows[:5]
        if not over:
            ui.label(t("dashboard_widgets.all_on_track")).classes(
                "text-positive text-sm font-medium"
            )
        with ui.column().classes("w-full gap-2 mt-1"):
            for row in over:
                pct = row.variance_pct
                pct_txt = "—" if pct is None else f"{float(pct):.0f}%"
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(row.category).classes("text-sm")
                    label = f"{fmt_amount(row.actual)} / {fmt_amount(row.planned)} ({pct_txt})"
                    ui.label(label).classes("text-sm text-red-600 font-medium")
