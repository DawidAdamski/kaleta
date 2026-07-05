# SPDX-License-Identifier: AGPL-3.0-or-later
"""Top merchants widget."""

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
    "top_merchants",
    "dashboard_widgets.top_merchants",
    "store",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_top_merchants(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    today = datetime.date.today()
    start = today - datetime.timedelta(days=30)
    merchants = await ReportService(session).top_merchants(start, today, limit=5)
    with section_card(
        t("dashboard_widgets.top_merchants"),
        subtitle=t("dashboard_widgets.top_merchants_sub"),
    ):
        if not merchants:
            ui.label(t("dashboard_widgets.no_merchants")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for m in merchants:
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(m.name).classes("text-sm truncate")
                    ui.label(fmt_amount(m.amount)).classes("text-sm font-medium")
