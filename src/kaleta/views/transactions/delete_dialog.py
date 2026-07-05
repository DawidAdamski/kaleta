# SPDX-License-Identifier: AGPL-3.0-or-later
"""Delete confirmation dialog for selected transactions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import TransactionService, with_session


def build_delete_dialog(
    selected_tx_ids: list[int],
    *,
    on_deleted: Callable[[], None],
) -> tuple[ui.dialog, Callable[[], None]]:
    """Create the multi-delete confirmation dialog."""
    delete_confirm_dialog = ui.dialog()
    with delete_confirm_dialog, ui.card().classes("w-[380px]"):
        delete_confirm_label = ui.label("").classes("text-base")

        async def _do_delete_selected() -> None:
            ids = list(selected_tx_ids)

            async def _delete(session: Any) -> None:
                svc = TransactionService(session)
                for tx_id in ids:
                    await svc.delete(tx_id)

            await with_session(_delete)
            delete_confirm_dialog.close()
            ui.notify(t("transactions.deleted"), type="positive")
            on_deleted()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=delete_confirm_dialog.close).props("flat")
            ui.button(t("common.delete"), icon="delete", on_click=_do_delete_selected).props(
                "color=negative"
            )

    def confirm_delete_selected() -> None:
        n = len(selected_tx_ids)
        delete_confirm_label.set_text(t("transactions.delete_confirm_multi", count=n))
        delete_confirm_dialog.open()

    return delete_confirm_dialog, confirm_delete_selected
