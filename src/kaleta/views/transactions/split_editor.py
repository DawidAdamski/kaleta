# SPDX-License-Identifier: AGPL-3.0-or-later
"""Split-transaction row editor inside the add-transaction dialog."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType
from kaleta.services import TransactionService


def build_split_editor(
    *,
    split_rows: list[dict[str, Any]],
    tx_type_sel: Any,
    income_cats: dict[int, str],
    expense_cats: dict[int, str],
    amount_input: Any,
    split_container: Any,
    on_balance_change: Callable[[], None] | None = None,
) -> tuple[Any, Any, Callable[[], None]]:
    """Wire split-row UI inside ``split_container``; return refresh callables."""

    def _notify_balance_change() -> None:
        if on_balance_change is not None:
            on_balance_change()

    @ui.refreshable
    def split_rows_ui() -> None:
        chosen = tx_type_sel.value
        cats = income_cats if chosen == TransactionType.INCOME.value else expense_cats

        for i, row in enumerate(split_rows):
            is_last = i == len(split_rows) - 1
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                cat_el = ui.select(
                    cats,
                    label=t("common.category"),
                    value=row["category_id"],
                ).classes("flex-1 min-w-0 split-cat-select")

                def _on_cat_change(e: Any, idx: int = i) -> None:
                    split_rows.__setitem__(idx, {**split_rows[idx], "category_id": e.value})

                cat_el.on_value_change(_on_cat_change)
                ui.input(
                    t("common.note"),
                    value=row["note"],
                    on_change=lambda e, idx=i: split_rows.__setitem__(
                        idx, {**split_rows[idx], "note": e.value}
                    ),
                ).classes("w-28")

                def _on_split_amount_change(e: Any, idx: int = i) -> None:
                    split_rows.__setitem__(idx, {**split_rows[idx], "amount": e.value})
                    split_balance_ui.refresh()
                    _notify_balance_change()

                amt_el = ui.number(
                    t("common.amount"),
                    value=row["amount"],
                    min=0.01,
                    step=0.01,
                    on_change=_on_split_amount_change,
                ).classes("w-28")
                if is_last:
                    amt_el.props("@keydown.tab.prevent=\"$emit('split_tab')\"")
                    amt_el.on("split_tab", lambda _: _handle_split_tab())
                ui.button(
                    icon="close",
                    on_click=lambda _, idx=i: _remove_split(idx),
                ).props("flat round dense size=sm color=negative tabindex=-1")

    @ui.refreshable
    def split_balance_ui() -> None:
        main_amount = Decimal(str(amount_input.value or 0))
        split_amounts = [Decimal(str(r["amount"] or 0)) for r in split_rows]
        balanced, remaining = TransactionService.split_balance(main_amount, split_amounts)

        with ui.row().classes("w-full items-center justify-between mt-1"):
            if main_amount > 0:
                color = "text-positive" if balanced else "text-warning"
                balance_text = (
                    "✓ " + t("transactions.balanced")
                    if balanced
                    else f"{remaining:+.2f} {t('transactions.remaining')}"
                )
                ui.label(balance_text).classes(f"text-sm {color}")
                if not balanced and remaining > 0:
                    ui.button(
                        t("transactions.fill_last"),
                        on_click=lambda r=remaining: _fill_last(r),
                    ).props("flat dense size=sm color=primary")
            else:
                ui.label(t("transactions.enter_total")).classes("text-sm text-slate-400")
            ui.button(
                t("transactions.add_split"),
                icon="add",
                on_click=lambda: _add_split(),
            ).props("flat dense size=sm color=primary")

    def _focus_first_split_cat() -> None:
        async def _do() -> None:
            await ui.run_javascript(
                "var els = document.querySelectorAll("
                "'.split-cat-select .q-field__native, .split-cat-select input');"
                "if(els.length > 0) els[0].focus();"
            )

        ui.timer(0.05, _do, once=True)

    def _focus_last_split_cat() -> None:
        async def _do() -> None:
            await ui.run_javascript(
                "var els = document.querySelectorAll("
                "'.split-cat-select .q-field__native, .split-cat-select input');"
                "if(els.length > 0) els[els.length - 1].focus();"
            )

        ui.timer(0.05, _do, once=True)

    def _remove_split(idx: int) -> None:
        split_rows.pop(idx)
        split_rows_ui.refresh()
        split_balance_ui.refresh()
        _notify_balance_change()

    def _fill_last(remaining: Decimal) -> None:
        if split_rows:
            split_rows[-1] = {**split_rows[-1], "amount": float(remaining)}
        split_balance_ui.refresh()
        _notify_balance_change()

    async def _add_split() -> None:
        split_rows.append({"category_id": None, "amount": None, "note": ""})
        split_rows_ui.refresh()
        split_balance_ui.refresh()
        _notify_balance_change()
        await ui.run_javascript(
            "var d=document.querySelector('.q-dialog .q-card');if(d) d.scrollTop=d.scrollHeight;"
        )

    def _handle_split_tab() -> None:
        split_rows.append({"category_id": None, "amount": None, "note": ""})
        split_rows_ui.refresh()
        split_balance_ui.refresh()
        _notify_balance_change()
        _focus_last_split_cat()

    with split_container:
        split_rows_ui()
        split_balance_ui()

    return split_rows_ui.refresh, split_balance_ui.refresh, _focus_first_split_cat
