"""Edit transaction dialog."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType, TransactionUpdate
from kaleta.services import TransactionService, with_session


@dataclass
class EditDialogContext:
    dialog: Any
    tag_sel: Any
    open_for_id: Callable[[int], Any]


def build_edit_dialog(
    account_options: dict[int, str],
    expense_cats: dict[int, str],
    income_cats: dict[int, str],
    tag_options: dict[int, str],
    *,
    on_saved: Callable[[], None],
) -> EditDialogContext:
    edit_tx_id: dict[str, int | None] = {"value": None}
    edit_dialog = ui.dialog()
    with edit_dialog, ui.card().classes("w-[520px]"):
        ui.label(t("transactions.edit")).classes("text-lg font-bold")

        edit_type_sel = ui.select(
            {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
            label=t("common.type"),
            value=TransactionType.EXPENSE.value,
        ).classes("w-full")

        edit_account_sel = ui.select(account_options, label=t("common.account")).classes("w-full")

        edit_category_sel = ui.select(expense_cats, label=t("common.category")).classes("w-full")

        edit_amount_input = ui.number(t("common.amount"), min=0.01, step=0.01).classes("w-full")

        edit_desc_input = ui.input(f"{t('common.description')} ({t('common.optional')})").classes(
            "w-full"
        )

        edit_date_input = ui.input(t("common.date")).props("type=date").classes("w-full")

        edit_tag_sel = (
            ui.select(
                tag_options,
                label=t("transactions.tags"),
                multiple=True,
                value=[],
            )
            .classes("w-full")
            .props("use-chips clearable")
        )

        edit_info = ui.label("").classes("text-sm text-grey-6 italic")
        edit_info.set_visibility(False)

        def _on_edit_type_change() -> None:
            chosen = edit_type_sel.value
            is_transfer = chosen == TransactionType.TRANSFER.value
            if chosen == TransactionType.INCOME.value:
                edit_category_sel.set_options(income_cats)
            elif chosen == TransactionType.EXPENSE.value:
                edit_category_sel.set_options(expense_cats)
            else:
                edit_category_sel.set_options({})
            edit_category_sel.set_visibility(not is_transfer)

        edit_type_sel.on("update:model-value", lambda _: _on_edit_type_change())

        async def edit_submit() -> None:
            tx_id = edit_tx_id["value"]
            if tx_id is None:
                return
            if not edit_account_sel.value:
                ui.notify(t("transactions.select_account"), type="negative")
                return
            if not edit_amount_input.value or edit_amount_input.value <= 0:
                ui.notify(t("transactions.enter_amount"), type="negative")
                return
            raw_date = edit_date_input.value
            try:
                parsed_date = (
                    datetime.date.fromisoformat(raw_date) if raw_date else datetime.date.today()
                )
            except ValueError:
                parsed_date = datetime.date.today()
            chosen_type = TransactionType(edit_type_sel.value)
            is_cat_visible = edit_category_sel.visible
            data = TransactionUpdate(
                account_id=edit_account_sel.value,
                amount=Decimal(str(edit_amount_input.value)),
                type=chosen_type,
                date=parsed_date,
                description=edit_desc_input.value or "",
                category_id=edit_category_sel.value if is_cat_visible else None,
                tag_ids=edit_tag_sel.value or [],
            )

            async def _update(session: Any) -> None:
                await TransactionService(session).update(tx_id, data)

            await with_session(_update)
            ui.notify(t("transactions.updated"), type="positive")
            edit_dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
            ui.button(t("common.save"), on_click=edit_submit).props("color=primary")

    async def open_for_id(tx_id: int) -> None:
        async def _load(session: Any) -> Any:
            return await TransactionService(session).get(tx_id)

        tx = await with_session(_load)
        if tx is None:
            return
        edit_tx_id["value"] = tx_id
        edit_account_sel.set_value(tx.account_id)
        edit_amount_input.set_value(float(tx.amount))
        edit_desc_input.set_value(tx.description or "")
        edit_date_input.set_value(str(tx.date))
        edit_type_sel.set_value(tx.type.value)
        edit_type_sel.set_visibility(not tx.is_internal_transfer)
        if tx.type == TransactionType.INCOME:
            edit_category_sel.set_options(income_cats)
        elif tx.type == TransactionType.EXPENSE:
            edit_category_sel.set_options(expense_cats)
        else:
            edit_category_sel.set_options({})
        edit_category_sel.set_value(tx.category_id)
        edit_category_sel.set_visibility(not tx.is_internal_transfer and not tx.is_split)
        edit_tag_sel.set_value([tg.id for tg in tx.tags])
        if tx.is_split:
            edit_info.set_text(t("transactions.split_edit_note"))
            edit_info.set_visibility(True)
        elif tx.is_internal_transfer:
            edit_info.set_text(t("transactions.transfer_edit_note"))
            edit_info.set_visibility(True)
        else:
            edit_info.set_visibility(False)
        edit_dialog.open()

    return EditDialogContext(dialog=edit_dialog, tag_sel=edit_tag_sel, open_for_id=open_for_id)
