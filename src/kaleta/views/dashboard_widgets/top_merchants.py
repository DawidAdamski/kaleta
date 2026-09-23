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
from kaleta.views.dashboard_widgets.helpers import fmt_number, section_card
from kaleta.views.dashboard_widgets.registry import RenderContext, register
from kaleta.views.theme import BODY_MUTED, HAIRLINE_BOTTOM, INK


@register(
    "top_merchants",
    "dashboard_widgets.top_merchants",
    "store",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_top_merchants(session: AsyncSession, ctx: RenderContext) -> None:
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
        # A hairline under every row but the last, and no currency on the
        # figures: artboard `1c` sets this card as a list, not a table, and
        # a column of five "zł" says the same thing five times.
        with ui.column().classes("w-full gap-0 mt-0.5"):
            for index, m in enumerate(merchants):
                rule = "" if index == len(merchants) - 1 else HAIRLINE_BOTTOM
                with ui.row().classes(
                    f"w-full items-center justify-between py-2.5 gap-3 no-wrap {rule}".strip()
                ):
                    ui.label(m.name).classes(f"{INK} text-[13.5px] truncate")
                    ui.label(fmt_number(m.amount)).classes(
                        f"k-mono {INK} text-[13.5px] font-medium"
                    )
