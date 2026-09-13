# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk-selection actions bar for the transactions table."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import TransactionService
from kaleta.views.theme import SELECTION_BAR, amount_class


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
        # The rows are the ones already on screen: "what did I just select"
        # is answered without a second query, by the same rule the group
        # separators use.
        total = TransactionService.net_of_rows(selected_rows)
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
            ui.label(TransactionService.format_net(total)).classes(
                f"{amount_class('income' if total >= 0 else 'expense')} text-[12.5px]"
            )

    table_actions_ui()
    return table_actions_ui
