# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recent transactions widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService
from kaleta.views.components.amount_label import amount_body_cell_slot, format_signed_amount
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import (
    BODY_MUTED,
    SECTION_CARD,
    SECTION_HEADING,
    SECTION_TITLE,
    TABLE_SURFACE,
)


@register(
    "recent_transactions",
    "dashboard_widgets.recent_transactions",
    "receipt_long",
    (4, 2),
    ((4, 2), (4, 3)),
)
async def render_recent_transactions(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    recent = await ReportService(session).recent_transactions(10)
    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between mb-3"):
            with ui.column().classes("gap-1"):
                ui.label(t("dashboard.recent_transactions")).classes(SECTION_TITLE)
                ui.label(t("dashboard_widgets.recent_transactions_sub")).classes(SECTION_HEADING)
            ui.button(
                t("dashboard.view_all"),
                icon="arrow_forward",
                on_click=lambda: ui.navigate.to("/transactions"),
            ).props("flat dense")

        if not recent:
            ui.label(t("dashboard.no_transactions")).classes(BODY_MUTED)
            return

        columns = [
            {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
            {
                "name": "account",
                "label": t("common.account"),
                "field": "account",
                "align": "left",
            },
            {
                "name": "desc",
                "label": t("common.description"),
                "field": "desc",
                "align": "left",
            },
            {
                "name": "category",
                "label": t("common.category"),
                "field": "category",
                "align": "left",
            },
            {
                "name": "amount",
                "label": t("common.amount"),
                "field": "amount",
                "align": "right",
            },
        ]
        rows = [
            {
                "date": str(tx.date),
                "account": tx.account.name if tx.account else "—",
                "desc": (tx.description or "—")[:45],
                "category": tx.category.name if tx.category else "—",
                "type": tx.type.value,
                "amount": format_signed_amount(tx.amount, tx.type.value),
            }
            for tx in recent
        ]
        tbl = ui.table(columns=columns, rows=rows).classes(TABLE_SURFACE).props("dense flat")
        tbl.add_slot("body-cell-amount", amount_body_cell_slot())
