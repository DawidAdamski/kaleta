"""Add transaction dialog with split and cross-currency transfer support."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate, TransactionType
from kaleta.services import CurrencyRateService, TransactionService, with_session
from kaleta.views.transactions.split_editor import build_split_editor


@dataclass
class AddDialogContext:
    dialog: Any
    tag_sel: Any
    open: Callable[[], Any]


def build_add_dialog(
    account_options: dict[int, str],
    accounts_by_id: dict[int, Any],
    expense_cats: dict[int, str],
    income_cats: dict[int, str],
    tag_options: dict[int, str],
    *,
    on_saved: Callable[[], None],
) -> AddDialogContext:
    split_rows: list[dict[str, Any]] = []
    is_split: dict[str, bool] = {"value": False}

    amount_input: Any
    dialog = ui.dialog()
    with dialog, ui.card().classes("w-[520px]"):
        ui.label(t("transactions.add")).classes("text-lg font-bold")

        tx_type_sel = ui.select(
            {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
            label=t("common.type"),
            value=TransactionType.EXPENSE.value,
        ).classes("w-full")

        account_sel = ui.select(account_options, label=t("common.account")).classes("w-full")
        if account_options:
            account_sel.value = next(iter(account_options))

        dest_row = ui.row().classes("w-full")
        dest_row.set_visibility(False)
        with dest_row:
            dest_account_sel = ui.select(
                account_options, label=t("transactions.to_account")
            ).classes("w-full")

        amount_input = (
            ui.number(t("common.amount"), min=0.01, step=0.01).classes("w-full").props("autofocus")
        )
        dialog.on("show", lambda: amount_input.run_method("focus"))

        def _on_amount_change(_: Any) -> None:
            refresh_split_balance()
            _update_fx()

        amount_input.on_value_change(_on_amount_change)

        desc_input = ui.input(f"{t('common.description')} ({t('common.optional')})").classes(
            "w-full"
        )

        category_sel = ui.select(expense_cats, label=t("common.category")).classes("w-full")

        today_str = str(datetime.date.today())
        date_text = ui.input(t("common.date")).props("type=date").classes("w-full")
        date_text.value = today_str

        add_tag_sel = (
            ui.select(
                tag_options,
                label=t("transactions.tags"),
                multiple=True,
                value=[],
            )
            .classes("w-full")
            .props("use-chips clearable")
        )

        split_switch = ui.switch(
            t("transactions.split"),
            on_change=lambda e: _on_split_toggle(e.value),
        )

        fx_row = ui.column().classes("w-full gap-2 border border-primary rounded p-3")
        fx_row.set_visibility(False)
        with fx_row:
            ui.label(t("transactions.cross_currency_transfer")).classes(
                "text-sm font-semibold text-primary"
            )
            with ui.row().classes("w-full gap-2 items-end"):
                fx_rate_input = ui.number(
                    t("transactions.exchange_rate"), min=0.000001, format="%.6f", step=0.01
                ).classes("flex-1")
                dest_amount_input = ui.number(
                    t("transactions.dest_amount", currency="?"), min=0.01, format="%.2f"
                ).classes("flex-1")
            fx_info = ui.label("").classes("text-xs text-grey-6")

        def _src_currency() -> str:
            src_id = account_sel.value
            return accounts_by_id[src_id].currency if src_id in accounts_by_id else "PLN"

        def _dst_currency() -> str:
            dst_id = dest_account_sel.value
            return accounts_by_id[dst_id].currency if dst_id in accounts_by_id else "PLN"

        def _is_cross_currency() -> bool:
            return (
                tx_type_sel.value == TransactionType.TRANSFER.value
                and dest_account_sel.value is not None
                and _src_currency() != _dst_currency()
            )

        def _update_fx() -> None:
            if not _is_cross_currency():
                return
            src_cur = _src_currency()
            dst_cur = _dst_currency()
            lbl = t("transactions.dest_amount", currency=dst_cur)
            dest_amount_input.props(f'label="{lbl}"')
            fx_rate_input.props(
                f'label="{t("transactions.exchange_rate_hint", src=src_cur, dst=dst_cur)}"'
            )
            src_amt = float(amount_input.value or 0)
            dst_amt = float(dest_amount_input.value or 0)
            rate_val = float(fx_rate_input.value or 0)
            if dst_amt > 0 and src_amt > 0 and dst_amt != rate_val * src_amt:
                computed_rate = dst_amt / src_amt
                fx_info.set_text(
                    t(
                        "transactions.rate_auto",
                        src=src_cur,
                        rate=f"{computed_rate:.6f}",
                        dst=dst_cur,
                    )
                )
            elif rate_val > 0 and src_amt > 0:
                fx_info.set_text(
                    t(
                        "transactions.rate_auto",
                        src=src_cur,
                        rate=f"{rate_val:.6f}",
                        dst=dst_cur,
                    )
                )

        def _on_fx_rate_change() -> None:
            src_amt = float(amount_input.value or 0)
            rate = float(fx_rate_input.value or 0)
            if src_amt > 0 and rate > 0:
                computed_dest = src_amt * rate
                dest_amount_input.set_value(round(computed_dest, 2))
            _update_fx()

        def _on_dest_amount_change() -> None:
            src_amt = float(amount_input.value or 0)
            dst_amt = float(dest_amount_input.value or 0)
            if src_amt > 0 and dst_amt > 0:
                computed_rate = dst_amt / src_amt
                fx_rate_input.set_value(round(computed_rate, 6))
            _update_fx()

        fx_rate_input.on_value_change(lambda _: _on_fx_rate_change())
        dest_amount_input.on_value_change(lambda _: _on_dest_amount_change())

        def on_type_change() -> None:
            chosen = tx_type_sel.value
            is_transfer = chosen == TransactionType.TRANSFER.value
            if chosen == TransactionType.INCOME.value:
                category_sel.set_options(income_cats)
            elif chosen == TransactionType.EXPENSE.value:
                category_sel.set_options(expense_cats)
            else:
                category_sel.set_options({})
            category_sel.value = None
            dest_row.set_visibility(is_transfer)
            category_sel.set_visibility(not is_transfer and not is_split["value"])
            split_switch.set_visibility(not is_transfer)
            _refresh_fx_visibility()

        def _refresh_fx_visibility() -> None:
            show = _is_cross_currency()
            fx_row.set_visibility(show)
            if show:
                _update_fx()

        tx_type_sel.on("update:model-value", lambda _: on_type_change())
        account_sel.on("update:model-value", lambda _: _refresh_fx_visibility())
        dest_account_sel.on("update:model-value", lambda _: _refresh_fx_visibility())

        split_container = ui.column().classes("w-full gap-1 border-t pt-3 mt-1")
        split_container.set_visibility(False)

        refresh_split_rows, refresh_split_balance, focus_first_split_cat = build_split_editor(
            split_rows=split_rows,
            tx_type_sel=tx_type_sel,
            income_cats=income_cats,
            expense_cats=expense_cats,
            amount_input=amount_input,
            split_container=split_container,
        )

        async def submit() -> None:
            if not account_sel.value:
                ui.notify(t("transactions.select_account"), type="negative")
                return
            if not amount_input.value or amount_input.value <= 0:
                ui.notify(t("transactions.enter_amount"), type="negative")
                return
            chosen_type = TransactionType(tx_type_sel.value)

            raw_date = date_text.value
            try:
                parsed_date = (
                    datetime.date.fromisoformat(raw_date) if raw_date else datetime.date.today()
                )
            except ValueError:
                parsed_date = datetime.date.today()

            if is_split["value"]:
                if not split_rows:
                    ui.notify(t("transactions.add_one_split"), type="negative")
                    return
                main_amount = Decimal(str(amount_input.value))
                split_amounts = [Decimal(str(r["amount"] or 0)) for r in split_rows]
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
                splits_payload = [
                    TransactionSplitCreate(
                        category_id=r["category_id"],
                        amount=Decimal(str(r["amount"])),
                        note=r["note"] or "",
                    )
                    for r in split_rows
                ]
                data = TransactionCreate(
                    account_id=account_sel.value,
                    category_id=None,
                    amount=amount_input.value,
                    type=chosen_type,
                    date=parsed_date,
                    description=desc_input.value or "",
                    is_split=True,
                    splits=splits_payload,
                    tag_ids=add_tag_sel.value or [],
                )
            else:
                if chosen_type == TransactionType.TRANSFER:
                    if not dest_account_sel.value:
                        ui.notify(t("transactions.select_dest_account"), type="negative")
                        return
                    if dest_account_sel.value == account_sel.value:
                        ui.notify(t("transactions.dest_same_as_src"), type="negative")
                        return
                    src_cur = _src_currency()
                    dst_cur = _dst_currency()
                    cross = src_cur != dst_cur
                    if cross:
                        rate = Decimal(str(fx_rate_input.value or 0))
                        if rate <= 0:
                            ui.notify(t("transactions.enter_rate_or_amount"), type="negative")
                            return
                        dest_amt = Decimal(str(dest_amount_input.value or 0))
                        if dest_amt <= 0:
                            dest_amt = Decimal(str(amount_input.value)) * rate
                    else:
                        rate = None
                        dest_amt = Decimal(str(amount_input.value))

                    outgoing = TransactionCreate(
                        account_id=account_sel.value,
                        amount=Decimal(str(amount_input.value)),
                        exchange_rate=rate,
                        type=TransactionType.TRANSFER,
                        date=parsed_date,
                        description=desc_input.value or "",
                        is_internal_transfer=True,
                    )
                    incoming = TransactionCreate(
                        account_id=dest_account_sel.value,
                        amount=dest_amt,
                        exchange_rate=rate,
                        type=TransactionType.TRANSFER,
                        date=parsed_date,
                        description=desc_input.value or "",
                        is_internal_transfer=True,
                    )

                    async def _create_transfer(session: Any) -> None:
                        await TransactionService(session).create_transfer(outgoing, incoming)
                        if cross and rate and rate > 0:
                            await CurrencyRateService(session).record_transfer_rate(
                                parsed_date, src_cur, dst_cur, rate
                            )

                    await with_session(_create_transfer)
                    ui.notify(t("transactions.saved"), type="positive")
                    dialog.close()
                    on_saved()
                    return
                if not category_sel.value:
                    ui.notify(t("transactions.select_category"), type="negative")
                    return
                data = TransactionCreate(
                    account_id=account_sel.value,
                    category_id=category_sel.value,
                    amount=amount_input.value,
                    type=chosen_type,
                    date=parsed_date,
                    description=desc_input.value or "",
                    tag_ids=add_tag_sel.value or [],
                )

            async def _create(session: Any) -> None:
                await TransactionService(session).create(data)

            await with_session(_create)
            ui.notify(t("transactions.saved"), type="positive")
            dialog.close()
            on_saved()

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
            ui.button(t("common.save"), on_click=submit).props("color=primary")

        ui.keyboard(on_key=lambda e: submit() if e.key == "Enter" and e.action.keydown else None)

    def _on_split_toggle(value: bool) -> None:
        is_split["value"] = value
        is_transfer = tx_type_sel.value == TransactionType.TRANSFER.value
        category_sel.set_visibility(not value and not is_transfer)
        split_container.set_visibility(value)
        if value:
            while len(split_rows) < 2:
                split_rows.append({"category_id": None, "amount": None, "note": ""})
            refresh_split_rows()
            refresh_split_balance()
            focus_first_split_cat()
        else:
            refresh_split_rows()
            refresh_split_balance()

    def _reset_dialog() -> None:
        split_rows.clear()
        is_split["value"] = False
        split_switch.set_value(False)
        category_sel.set_visibility(True)
        split_switch.set_visibility(True)
        split_container.set_visibility(False)
        dest_row.set_visibility(False)
        fx_row.set_visibility(False)
        dest_account_sel.set_value(None)
        fx_rate_input.set_value(None)
        dest_amount_input.set_value(None)
        fx_info.set_text("")
        add_tag_sel.set_value([])
        refresh_split_rows()
        refresh_split_balance()

    dialog.on("hide", lambda: _reset_dialog())

    return AddDialogContext(dialog=dialog, tag_sel=add_tag_sel, open=dialog.open)
