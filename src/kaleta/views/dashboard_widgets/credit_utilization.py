# SPDX-License-Identifier: AGPL-3.0-or-later
"""Credit utilization widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import CreditService
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED


@register(
    "credit_utilization",
    "dashboard_widgets.credit_utilization",
    "credit_card",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_credit_utilization(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    cards = await CreditService(session).list_cards()
    with section_card(
        t("dashboard_widgets.credit_utilization"),
        subtitle=t("dashboard_widgets.credit_utilization_sub"),
    ):
        if not cards:
            ui.label(t("dashboard_widgets.credit_utilization_empty")).classes(f"{BODY_MUTED} mt-2")
            return
        for card in cards:
            pct = float(card.utilization_pct)
            pct_clamped = min(pct, 1.0)
            if pct >= 0.7:
                colour = "negative"
            elif pct >= 0.3:
                colour = "amber-7"
            else:
                colour = "positive"
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(card.account_name).classes("flex-1 text-sm font-medium")
                ui.label(f"{int(round(pct * 100))}%").classes(
                    f"text-sm font-bold text-{colour} w-12 text-right"
                )
            ui.linear_progress(
                value=pct_clamped, size="6px", show_value=False, color=colour
            ).classes("w-full")
