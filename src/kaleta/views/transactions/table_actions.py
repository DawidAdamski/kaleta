# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk-selection actions bar for the transactions table."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t


def render_table_actions(
    selected_tx_ids: list[int],
    *,
    on_delete: Callable[[], None],
    refresh: Callable[[], None],
) -> Any:
    """Render the delete-selected bar when one or more rows are checked."""

    @ui.refreshable
    def table_actions_ui() -> None:
        n = len(selected_tx_ids)
        if n:
            with ui.row().classes("w-full items-center gap-2 py-1"):
                ui.label(t("transactions.delete_selected", count=n)).classes(
                    "text-sm text-slate-600 font-medium"
                )
                ui.button(icon="delete", on_click=on_delete).props(
                    "flat round dense color=negative size=sm"
                )

                def _clear_selection() -> None:
                    selected_tx_ids.clear()
                    refresh()

                ui.button(icon="close", on_click=_clear_selection).props(
                    "flat round dense color=grey size=sm"
                )

    table_actions_ui()
    return table_actions_ui
