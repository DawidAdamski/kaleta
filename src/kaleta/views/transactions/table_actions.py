# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk-selection actions bar for the transactions table."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import TransactionService
from kaleta.views.components.amount_label import net_tone
from kaleta.views.theme import (
    SELECTION_ACTION,
    SELECTION_ACTION_DANGER,
    SELECTION_BAR,
    SELECTION_DIVIDER,
)


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
        with ui.row().classes(
            f"{SELECTION_BAR} w-full items-center gap-[14px] px-[18px] py-[11px] rounded-[10px]"
        ):
            ui.label(t("transactions.selected_count", count=n)).classes("text-[12.5px] font-medium")
            # The hairline artboard `2a` puts between the count and the
            # actions: the count says what you have, the rest what you can do
            # with it, and the two are not one list.
            ui.element("span").classes(SELECTION_DIVIDER)
            delete_button = (
                ui.button(t("common.delete"), icon="delete", on_click=on_delete, color=None)
                .props("flat dense no-caps")
                .classes(SELECTION_ACTION_DANGER)
            )
            delete_button.tooltip(t("transactions.delete_selected", count=n))

            def _clear_selection() -> None:
                # The page owns the table, so it is the one that can take the
                # ticks off the rows as well as forget their ids.
                on_clear()
                refresh()

            # No counterpart on the artboard, which draws a selection it never
            # has to let go of. Dismissing one is the app's own need, so it
            # takes the quietest shape on the bar.
            clear_button = (
                ui.button(icon="close", on_click=_clear_selection, color=None)
                .props("flat round dense size=sm")
                .classes(SELECTION_ACTION)
            )
            clear_button.tooltip(t("transactions.clear_selection"))
            clear_button.props["aria-label"] = t("transactions.clear_selection")
            ui.space()
            ui.label(t("transactions.selected_total")).classes("k-muted text-[12px]").tooltip(
                t("transactions.selected_net")
            )
            # A selection of transfers nets to zero — which is neither money
            # in nor money out, and must not be painted as either.
            ui.label(TransactionService.format_net(total)).classes(
                f"{net_tone(total)} text-[12.5px]"
            )

    table_actions_ui()
    return table_actions_ui
