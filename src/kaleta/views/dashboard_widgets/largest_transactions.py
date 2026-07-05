# SPDX-License-Identifier: AGPL-3.0-or-later
"""Largest transactions widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType
from kaleta.services import ReportService
from kaleta.views.components.amount_label import amount_css_class
from kaleta.views.dashboard_widgets.helpers import fmt_amount, section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED


@register(
    "largest_transactions",
    "dashboard_widgets.largest_transactions",
    "format_list_numbered",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_largest_transactions(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    rows = await ReportService(session).largest_transactions(
        days=30, limit=5, tx_type=TransactionType.EXPENSE
    )
    expense_cls = amount_css_class("expense")
    with section_card(
        t("dashboard_widgets.largest_transactions"),
        subtitle=t("dashboard_widgets.largest_transactions_sub"),
    ):
        if not rows:
            ui.label(t("dashboard_widgets.no_transactions")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for r in rows:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(r.description or r.category).classes("text-sm truncate")
                        ui.label(f"{r.date} · {r.category}").classes("text-xs text-slate-500")
                    ui.label(fmt_amount(r.amount)).classes(f"text-sm font-medium {expense_cls}")
