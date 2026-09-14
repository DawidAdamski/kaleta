# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk-selection actions bar for the transactions table."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import TransactionService
from kaleta.views.theme import AMOUNT_NEUTRAL, SELECTION_BAR, amount_class


def render_table_actions(
    selected_tx_ids: list[int],
    selected_rows: list[dict[str, Any]],
    *,
    on_delete: Callable[[], None],
    on_clear: Callable[[], None],
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
            delete_button = ui.button(icon="delete", on_click=on_delete).props(
                "flat round dense color=negative size=sm"
            )
            delete_button.tooltip(t("transactions.delete_selected", count=n))
            # An icon button with only a tooltip has no name to announce.
            delete_button.props["aria-label"] = t("transactions.delete_selected", count=n)

            def _clear_selection() -> None:
                # The page owns the table, so it is the one that can take the
                # ticks off the rows as well as forget their ids.
                on_clear()
                refresh()

            clear_button = ui.button(icon="close", on_click=_clear_selection).props(
                "flat round dense color=grey size=sm"
            )
            clear_button.tooltip(t("transactions.clear_selection"))
            clear_button.props["aria-label"] = t("transactions.clear_selection")
            ui.space()
            ui.label(t("transactions.selected_total")).classes("k-muted text-[12px]").tooltip(
                t("transactions.group_net")
            )
            # A selection of transfers nets to zero — which is neither money
            # in nor money out, and must not be painted as either.
            if total > 0:
                tone = amount_class("income")
            elif total < 0:
                tone = amount_class("expense")
            else:
                tone = AMOUNT_NEUTRAL
            ui.label(TransactionService.format_net(total)).classes(f"{tone} text-[12.5px]")

    table_actions_ui()
    return table_actions_ui
