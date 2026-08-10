# SPDX-License-Identifier: AGPL-3.0-or-later
"""Edit transaction dialog."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.categorisation_rule import (
    CategorisationRuleCreate,
    CategorisationRuleSuggestion,
    RuleMatchMode,
)
from kaleta.schemas.transaction import TransactionSplitCreate, TransactionType, TransactionUpdate
from kaleta.services import RuleService, TransactionService, with_session
from kaleta.views.transactions.split_editor import build_split_editor


@dataclass
class EditDialogContext:
    dialog: Any
    tag_sel: Any
    open_for_id: Callable[..., Any]


def build_edit_dialog(
    account_options: dict[int, str],
    expense_cats: dict[int, str],
    income_cats: dict[int, str],
    tag_options: dict[int, str],
    *,
    on_saved: Callable[[], None],
) -> EditDialogContext:
    edit_tx_id: dict[str, int | None] = {"value": None}
    edit_is_split: dict[str, bool] = {"value": False}
    edit_original_category_id: dict[str, int | None] = {"value": None}
    edit_payee_name: dict[str, str | None] = {"value": None}
    edit_split_rows: list[dict[str, Any]] = []
    edit_dialog = ui.dialog()
    suggest_dialog = ui.dialog()
    pending_suggestion: dict[str, CategorisationRuleSuggestion | None] = {"value": None}

    with suggest_dialog, ui.card().classes("w-[440px] gap-3"):
        ui.label(t("rules.suggest_title")).classes("text-lg font-bold")
        suggest_body = ui.label("").classes("text-sm")

        async def _create_suggested_rule() -> None:
            suggestion = pending_suggestion["value"]
            if suggestion is None:
                suggest_dialog.close()
                return

            async def _create(session: Any) -> None:
                await RuleService(session).create(
                    CategorisationRuleCreate(
                        pattern=suggestion.pattern,
                        category_id=suggestion.category_id,
                        match_mode=RuleMatchMode.CONTAINS,
                    )
                )

            await with_session(_create)
            ui.notify(t("rules.created"), type="positive")
            suggest_dialog.close()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(t("rules.suggest_dismiss"), on_click=suggest_dialog.close).props("flat")
            ui.button(
                t("rules.suggest_create"),
                on_click=_create_suggested_rule,
            ).props("color=primary")

    with edit_dialog, ui.card().classes("w-[520px]"):
        ui.label(t("transactions.edit")).classes("text-lg font-bold")

        edit_type_sel = ui.select(
            {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
            label=t("common.type"),
            value=TransactionType.EXPENSE.value,
        ).classes("w-full")

        edit_account_sel = ui.select(account_options, label=t("common.account")).classes("w-full")

        with ui.row().classes("w-full items-start gap-3 no-wrap"):
            edit_category_sel = ui.select(expense_cats, label=t("common.category")).classes(
                "flex-1"
            )
            with ui.column().classes("gap-0 shrink-0 pt-1"):
                edit_split_switch = ui.switch(
                    t("transactions.split"),
                    on_change=lambda e: _on_edit_split_toggle(bool(e.value)),
                )
                ui.label(t("transactions.split_tooltip")).classes(
                    "text-xs text-slate-500 max-w-[11rem] leading-tight"
                )

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

        edit_info = ui.label("").classes("text-sm text-slate-500 italic")
        edit_info.set_visibility(False)

        edit_split_container = ui.column().classes("w-full gap-1 border-t pt-3 mt-1")
        edit_split_container.set_visibility(False)

        def _update_save_enabled() -> None:
            if not edit_is_split["value"]:
                edit_save_btn.enable()
                return
            main_amount = Decimal(str(edit_amount_input.value or 0))
            split_amounts = [Decimal(str(r["amount"] or 0)) for r in edit_split_rows]
            balanced, _ = TransactionService.split_balance(main_amount, split_amounts)
            if balanced and edit_split_rows:
                edit_save_btn.enable()
            else:
                edit_save_btn.disable()

        (
            refresh_edit_split_rows,
            refresh_edit_split_balance,
            focus_first_split_cat,
        ) = build_split_editor(
            split_rows=edit_split_rows,
            tx_type_sel=edit_type_sel,
            income_cats=income_cats,
            expense_cats=expense_cats,
            amount_input=edit_amount_input,
            split_container=edit_split_container,
            on_balance_change=_update_save_enabled,
        )

        def _on_edit_amount_change(_: Any) -> None:
            refresh_edit_split_balance()
            _update_save_enabled()

        edit_amount_input.on_value_change(_on_edit_amount_change)

        def _on_edit_split_toggle(value: bool) -> None:
            edit_is_split["value"] = value
            is_transfer = edit_type_sel.value == TransactionType.TRANSFER.value
            edit_category_sel.set_visibility(not value and not is_transfer)
            edit_split_container.set_visibility(value)
            if value:
                while len(edit_split_rows) < 2:
                    edit_split_rows.append({"category_id": None, "amount": None, "note": ""})
                refresh_edit_split_rows()
                refresh_edit_split_balance()
                focus_first_split_cat()
            else:
                refresh_edit_split_rows()
                refresh_edit_split_balance()
            _update_save_enabled()

        def _on_edit_type_change() -> None:
            chosen = edit_type_sel.value
            is_transfer = chosen == TransactionType.TRANSFER.value
            if chosen == TransactionType.INCOME.value:
                edit_category_sel.set_options(income_cats)
            elif chosen == TransactionType.EXPENSE.value:
                edit_category_sel.set_options(expense_cats)
            else:
                edit_category_sel.set_options({})
            edit_category_sel.set_visibility(not is_transfer and not edit_is_split["value"])
            edit_split_switch.set_visibility(not is_transfer)
            if is_transfer and edit_is_split["value"]:
                edit_split_switch.set_value(False)
                _on_edit_split_toggle(False)
            elif edit_is_split["value"]:
                refresh_edit_split_rows()

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
            if edit_is_split["value"]:
                if not edit_split_rows:
                    ui.notify(t("transactions.add_one_split"), type="negative")
                    return
                main_amount = Decimal(str(edit_amount_input.value))
                split_amounts = [Decimal(str(r["amount"] or 0)) for r in edit_split_rows]
                balanced, remaining = TransactionService.split_balance(main_amount, split_amounts)
                if not balanced:
                    total_split = main_amount - remaining
                    ui.notify(
                        t(
                            "transactions.splits_must_sum",
                            total=f"{main_amount:.2f}",
                            current=f"{total_split:.2f}",
                        ),
                        type="negative",
                    )
                    return
                data.splits = [
                    TransactionSplitCreate(
                        category_id=r["category_id"],
                        amount=Decimal(str(r["amount"])),
                        note=r["note"] or "",
                    )
                    for r in edit_split_rows
                ]
                data.is_split = True
                data.category_id = None
            else:
                data.is_split = False
                if (
                    chosen_type in (TransactionType.INCOME, TransactionType.EXPENSE)
                    and not edit_category_sel.value
                ):
                    ui.notify(t("transactions.select_category"), type="negative")
                    return

            async def _update(session: Any) -> CategorisationRuleSuggestion | None:
                await TransactionService(session).update(tx_id, data)
                new_category_id = data.category_id
                if (
                    edit_is_split["value"]
                    or new_category_id is None
                    or new_category_id == edit_original_category_id["value"]
                ):
                    return None
                return await RuleService(session).suggest_from_corrections(
                    payee_name=edit_payee_name["value"],
                    description=data.description or "",
                    category_id=new_category_id,
                )

            suggestion = await with_session(_update)
            ui.notify(t("transactions.updated"), type="positive")
            edit_dialog.close()
            on_saved()
            if suggestion is not None:
                pending_suggestion["value"] = suggestion
                suggest_body.set_text(
                    t(
                        "rules.suggest_body",
                        pattern=suggestion.pattern,
                        category=suggestion.category_name,
                        count=suggestion.match_count,
                    )
                )
                suggest_dialog.open()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
            edit_save_btn = ui.button(t("common.save"), on_click=edit_submit).props("color=primary")

    async def open_for_id(tx_id: int, *, arm_split: bool = False) -> None:
        async def _load(session: Any) -> Any:
            return await TransactionService(session).get(tx_id)

        tx = await with_session(_load)
        if tx is None:
            return
        edit_tx_id["value"] = tx_id
        edit_original_category_id["value"] = tx.category_id
        edit_payee_name["value"] = tx.payee.name if tx.payee else None
        edit_split_rows.clear()
        if tx.is_split:
            for split in tx.splits:
                edit_split_rows.append(
                    {
                        "category_id": split.category_id,
                        "amount": float(split.amount),
                        "note": split.note,
                    }
                )
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
        edit_tag_sel.set_value([tg.id for tg in tx.tags])

        is_transfer = tx.type == TransactionType.TRANSFER or tx.is_internal_transfer
        want_split = (tx.is_split or arm_split) and not is_transfer
        edit_is_split["value"] = want_split
        edit_split_switch.set_visibility(not is_transfer)
        edit_split_switch.set_value(want_split)
        edit_category_sel.set_visibility(not is_transfer and not want_split)
        edit_split_container.set_visibility(want_split)

        if want_split:
            if arm_split and not tx.is_split:
                while len(edit_split_rows) < 2:
                    edit_split_rows.append({"category_id": None, "amount": None, "note": ""})
            refresh_edit_split_rows()
            refresh_edit_split_balance()
            if arm_split and not tx.is_split:
                focus_first_split_cat()
            edit_info.set_visibility(False)
        elif tx.is_internal_transfer:
            edit_info.set_text(t("transactions.transfer_edit_note"))
            edit_info.set_visibility(True)
        else:
            edit_info.set_visibility(False)
        _update_save_enabled()
        edit_dialog.open()

    return EditDialogContext(dialog=edit_dialog, tag_sel=edit_tag_sel, open_for_id=open_for_id)
