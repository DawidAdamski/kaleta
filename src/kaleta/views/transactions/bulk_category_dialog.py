# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bulk "change category" dialog for selected transactions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.services import TransactionService, with_session
from kaleta.views.error_handling import notify_kaleta_error


def assignable_category_type(selected_rows: list[dict[str, Any]]) -> str | None:
    """The one category type a selection can take, or ``None`` when it can't.

    A category is typed income or expense, so a batch can only be recategorised
    when every selected row is the same income/expense type — a transfer has no
    user category, and a split carries one per line. Mixed or unassignable
    selections return ``None`` and the bar leaves the action disabled.
    """
    types = {row.get("type") for row in selected_rows}
    if any(row.get("has_splits") for row in selected_rows):
        return None
    if types == {"income"}:
        return "income"
    if types == {"expense"}:
        return "expense"
    return None


def build_bulk_category_dialog(
    selected_tx_ids: list[int],
    selected_rows: list[dict[str, Any]],
    expense_cats: dict[int, str],
    income_cats: dict[int, str],
    *,
    on_applied: Callable[[], Awaitable[None]],
) -> tuple[ui.dialog, Callable[[], None]]:
    """Create the dialog that assigns one category to every selected row."""
    dialog = ui.dialog()
    chosen: dict[str, int | None] = {"value": None}

    with dialog, ui.card().classes("w-[420px] gap-3"):
        ui.label(t("transactions.change_category_title")).classes("text-base font-medium")
        hint = ui.label("").classes("k-muted text-[12.5px]")
        category_select = (
            ui.select({}, label=t("common.category"), with_input=True)
            .props("outlined dense")
            .classes("w-full")
        )
        category_select.bind_value(chosen, "value")

        async def _apply() -> None:
            category_id = chosen["value"]
            if category_id is None:
                return
            ids = list(selected_tx_ids)

            async def _assign(session: Any) -> int:
                return await TransactionService(session).set_category_bulk(ids, category_id)

            try:
                changed = await with_session(_assign)
            except KaletaError as exc:
                notify_kaleta_error(exc)
                return
            dialog.close()
            ui.notify(t("transactions.category_assigned", count=changed), type="positive")
            await on_applied()

        with ui.row().classes("w-full justify-end gap-2 mt-1"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            apply_button = ui.button(t("transactions.change_category_apply"), on_click=_apply)
            apply_button.bind_enabled_from(chosen, "value", backward=lambda v: v is not None)

    def open_dialog() -> None:
        cat_type = assignable_category_type(selected_rows)
        if cat_type is None:
            # The bar keeps the button disabled for these, so this is only a
            # guard against a stale open; say nothing and stay shut.
            return
        options = income_cats if cat_type == "income" else expense_cats
        chosen["value"] = None
        category_select.set_options(dict(options), value=None)
        hint.set_text(t("transactions.change_category_hint", count=len(selected_tx_ids)))
        dialog.open()

    return dialog, open_dialog
