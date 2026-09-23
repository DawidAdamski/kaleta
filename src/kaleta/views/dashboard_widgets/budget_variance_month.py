# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget variance month widget."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kaleta.services.report_service import BudgetVarianceRow

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.dashboard_widgets.constants import SEVERE_SPENT_PCT
from kaleta.views.dashboard_widgets.helpers import fmt_amount, fmt_number, section_card
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_WARNING,
    BODY_MUTED,
    CARD_SUBTITLE,
    INK,
    PACE_BAR_ROW,
)


@register(
    "budget_variance_month",
    "dashboard_widgets.budget_variance_month",
    "rule",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_budget_variance_month(session: AsyncSession, ctx: RenderContext) -> None:
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
        with ui.column().classes("w-full gap-4 mt-1"):
            for row in over:
                _variance_row(row)


def _variance_row(row: BudgetVarianceRow) -> None:
    """Category, overspend, a full ``.k-pace`` bar, and the spend against plan.

    Artboard ``1c``: the bar is the overspend itself — every row shown here is
    already past its budget, so the track runs full and only its colour
    carries how far past. The numbers sit under it in mono.
    """
    spent = row.spent_pct
    spent_txt = "—" if spent is None else f"{float(spent):.0f}%"
    severe = row.is_severely_over(SEVERE_SPENT_PCT)
    colour = "var(--k-expense)" if severe else "var(--k-warning)"
    amount_cls = AMOUNT_EXPENSE if severe else AMOUNT_WARNING

    with ui.column().classes("w-full gap-1.5"):
        with ui.row().classes("w-full items-baseline justify-between no-wrap gap-3"):
            ui.label(row.category).classes(f"{INK} text-[13px] truncate")
            ui.label(f"+{fmt_number(row.overspend)}").classes(f"k-mono {amount_cls} text-[13px]")
        with ui.element("div").classes(f"{PACE_BAR_ROW} w-full"):
            ui.element("div").classes("k-pace__fill").style(f"width:100%;background:{colour}")
        ui.label(f"{fmt_amount(row.actual)} / {fmt_amount(row.planned)} · {spent_txt}").classes(
            f"k-mono {CARD_SUBTITLE} text-[11px]"
        )
