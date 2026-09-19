# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recent transactions widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import ReportService, TransactionService
from kaleta.views.components.amount_label import amount_body_cell_slot, format_signed_amount
from kaleta.views.dashboard_widgets.registry import register
from kaleta.views.theme import (
    ACCENT_TEXT,
    BODY_MUTED,
    CARD_TITLE,
    CELL_CHIP,
    CELL_DATE,
    DASH_CARD,
    MUTED,
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
    with ui.card().classes(DASH_CARD):
        # Title and link on one baseline, as artboard `1c` sets them. The
        # card carried an eyebrow and a second line ("Last 10 movements")
        # that the artboard does not: the title says what this is, and the
        # row count is not a claim worth a line of its own.
        with ui.row().classes("w-full items-baseline justify-between mb-4"):
            ui.label(t("dashboard.recent_transactions")).classes(CARD_TITLE)
            ui.button(
                t("dashboard.view_all"),
                on_click=lambda: ui.navigate.to("/transactions"),
                color=None,
            ).props("flat dense no-caps icon-right=arrow_forward").classes(
                f"{ACCENT_TEXT} text-[12.5px] font-medium"
            )

        if not recent:
            ui.label(t("dashboard.no_transactions")).classes(BODY_MUTED)
            return

        # Date, Description, Account, Category, Amount — the artboard's order.
        # Description before Account: the payee is what you scan a ledger for,
        # and which of your own accounts it came out of is context.
        columns = [
            {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
            {
                "name": "desc",
                "label": t("common.description"),
                "field": "desc",
                "align": "left",
            },
            {
                "name": "account",
                "label": t("common.account"),
                "field": "account",
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
                # "09-26": the year is the same six times over in a card
                # showing the last ten movements.
                "date": tx.date.strftime("%m-%d"),
                "account": tx.account.name if tx.account else "—",
                "desc": (tx.description or "—")[:45],
                "category": tx.category.name if tx.category else "—",
                "type": tx.type.value,
                "amount": format_signed_amount(tx.amount, tx.type),
                # The cell paints a zero neutral, and needs the figure to see it.
                "amount_value": str(TransactionService.signed_amount(tx.amount, tx.type)),
            }
            for tx in recent
        ]
        tbl = ui.table(columns=columns, rows=rows).classes(TABLE_SURFACE).props("dense flat")
        tbl.add_slot("body-cell-amount", amount_body_cell_slot())
        tbl.add_slot(
            "body-cell-date",
            f'<q-td :props="props"><span class="{CELL_DATE}">'
            "{{ props.row.date }}</span></q-td>",
        )
        # An em dash is the absence of a category, not a category — so it is
        # not given a pill to sit in.
        tbl.add_slot(
            "body-cell-category",
            '<q-td :props="props"><span v-if="props.row.category === \'—\'" '
            f'class="{MUTED}">—</span>'
            f'<span v-else class="{CELL_CHIP}">{{{{ props.row.category }}}}</span></q-td>',
        )
