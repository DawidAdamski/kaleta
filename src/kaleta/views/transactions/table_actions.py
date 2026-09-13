# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk-selection actions bar for the transactions table."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import SELECTION_BAR, amount_class


def selection_total(rows: list[dict[str, Any]]) -> Decimal:
    """Signed sum of the selected rows, as they are shown.

    The rows are the ones already on screen, so this answers "what did I just
    select" without a second query — and without the total being able to
    disagree with the column above it.
    """
    return sum((Decimal(str(row.get("amount_value", 0))) for row in rows), start=Decimal("0"))


def render_table_actions(
    selected_tx_ids: list[int],
    selected_rows: list[dict[str, Any]],
    *,
    on_delete: Callable[[], None],
    refresh: Callable[[], None],
) -> Any:
    """Render the warm selection bar when one or more rows are checked."""

    @ui.refreshable
    def table_actions_ui() -> None:
        n = len(selected_tx_ids)
        if not n:
            return
        total = selection_total(selected_rows)
        with ui.row().classes(f"{SELECTION_BAR} w-full items-center gap-3 px-4 py-2 rounded-lg"):
            ui.label(t("transactions.selected_count", count=n)).classes("text-[12.5px] font-medium")
            ui.button(icon="delete", on_click=on_delete).props(
                "flat round dense color=negative size=sm"
            ).tooltip(t("transactions.delete_selected", count=n))

            def _clear_selection() -> None:
                selected_tx_ids.clear()
                selected_rows.clear()
                refresh()

            ui.button(icon="close", on_click=_clear_selection).props(
                "flat round dense color=grey size=sm"
            )
            ui.space()
            ui.label(t("transactions.selected_total")).classes("k-muted text-[12px]")
            ui.label(f"{total:+,.2f}").classes(
                f"{amount_class('income' if total >= 0 else 'expense')} text-[12.5px]"
            )

    table_actions_ui()
    return table_actions_ui
