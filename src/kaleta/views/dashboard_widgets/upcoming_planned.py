# SPDX-License-Identifier: AGPL-3.0-or-later
"""Upcoming planned transactions widget."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType
from kaleta.services.planned_transaction_service import PlannedTransactionService
from kaleta.views.components.amount_label import amount_css_class, format_signed_amount
from kaleta.views.dashboard_widgets.helpers import section_card
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import BODY_MUTED


@register(
    "upcoming_planned",
    "dashboard_widgets.upcoming_planned",
    "event_upcoming",
    (2, 2),
    ((2, 2), (4, 2)),
)
async def render_upcoming_planned(session: AsyncSession, is_dark: bool) -> None:  # noqa: ARG001
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=14)
    occs = await PlannedTransactionService(session).get_occurrences(
        today, horizon, account_id=None, active_only=True
    )
    with section_card(
        t("dashboard_widgets.upcoming_planned"),
        subtitle=t("dashboard_widgets.upcoming_planned_sub"),
    ):
        if not occs:
            ui.label(t("dashboard_widgets.nothing_planned")).classes(BODY_MUTED)
            return
        with ui.column().classes("w-full gap-1 mt-1"):
            for occ in occs[:6]:
                is_income = occ.type == TransactionType.INCOME
                tx_type = (
                    TransactionType.INCOME.value if is_income else TransactionType.EXPENSE.value
                )
                amount_cls = amount_css_class(tx_type)
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0"):
                        ui.label(occ.name).classes("text-sm")
                        ui.label(str(occ.date)).classes("text-xs text-slate-500")
                    ui.label(f"{format_signed_amount(occ.amount, tx_type)} zł").classes(
                        f"text-sm font-medium {amount_cls}"
                    )
