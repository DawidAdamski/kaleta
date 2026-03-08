from __future__ import annotations

import datetime
from decimal import Decimal

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.account import Account
from kaleta.models.category import CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.views.layout import page_layout

PAGE_SIZE = 50
_KBD_CLS = "text-xs bg-grey-2 border border-grey-4 rounded px-2 py-0.5 font-mono text-grey-7"


def _no_data_slot() -> str:
    return (
        f'<div class="text-center text-grey-6 py-8">{t("transactions.no_results")}</div>'
    )


def _category_label(tx: Transaction) -> str:
    if tx.is_split and tx.splits:
        names = [s.category.name for s in tx.splits if s.category]
        return f"(Split: {', '.join(names)})" if names else "(Split)"
    return tx.category.name if tx.category else "—"


def register() -> None:
    @ui.page("/transactions")
    async def transactions_page() -> None:
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            categories = await CategoryService(session).list()

        account_options: dict[int, str] = {a.id: a.name for a in accounts}
        expense_cats: dict[int, str] = {
            c.id: c.name for c in categories if c.type == CategoryType.EXPENSE
        }
        income_cats: dict[int, str] = {
            c.id: c.name for c in categories if c.type == CategoryType.INCOME
        }
        all_cats: dict[int, str] = {c.id: c.name for c in categories}

        # ── Filter state ──────────────────────────────────────────────────────
        filters: dict = {
            "date_from": None,
            "date_to": None,
            "account_ids": [],
            "category_ids": [],
            "tx_types": [],
            "search": "",
            "page": 0,
        }

        def active_filter_count() -> int:
            return sum(
                [
                    filters["date_from"] is not None,
                    filters["date_to"] is not None,
                    bool(filters["account_ids"]),
                    bool(filters["category_ids"]),
                    bool(filters["tx_types"]),
                    bool(filters["search"]),
                ]
            )

        def _list_or_none(key: str) -> list | None:
            return filters[key] if filters[key] else None

        # ── Refreshable table ─────────────────────────────────────────────────
        @ui.refreshable
        async def transaction_table() -> None:
            async with AsyncSessionFactory() as session:
                svc = TransactionService(session)
                total = await svc.count(
                    account_ids=_list_or_none("account_ids"),
                    category_ids=_list_or_none("category_ids"),
                    date_from=filters["date_from"],
                    date_to=filters["date_to"],
                    tx_types=_list_or_none("tx_types"),
                    search=filters["search"] or None,
                )
                txs = await svc.list(
                    account_ids=_list_or_none("account_ids"),
                    category_ids=_list_or_none("category_ids"),
                    date_from=filters["date_from"],
                    date_to=filters["date_to"],
                    tx_types=_list_or_none("tx_types"),
                    search=filters["search"] or None,
                    limit=PAGE_SIZE,
                    offset=filters["page"] * PAGE_SIZE,
                )

            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            current_page = filters["page"]
            start_n = current_page * PAGE_SIZE + 1
            end_n = min(start_n + PAGE_SIZE - 1, total)

            columns = [
                {
                    "name": "date",
                    "label": t("common.date"),
                    "field": "date",
                    "sortable": True,
                },
                {
                    "name": "account",
                    "label": t("common.account"),
                    "field": "account",
                    "align": "left",
                },
                {
                    "name": "description",
                    "label": t("common.description"),
                    "field": "description",
                    "align": "left",
                },
                {
                    "name": "category",
                    "label": t("common.category"),
                    "field": "category",
                    "align": "left",
                },
                {
                    "name": "type",
                    "label": t("common.type"),
                    "field": "type",
                    "align": "left",
                },
                {
                    "name": "amount",
                    "label": t("common.amount"),
                    "field": "amount",
                    "align": "right",
                    "sortable": True,
                },
            ]
            rows = [
                {
                    "id": tx.id,
                    "date": str(tx.date),
                    "account": tx.account.name if tx.account else "—",
                    "description": tx.description or "—",
                    "category": _category_label(tx),
                    "type": tx.type.value,
                    "amount": (
                        f"+{abs(tx.amount):,.2f}"
                        if tx.type == TransactionType.INCOME
                        else f"-{abs(tx.amount):,.2f}"
                    ),
                }
                for tx in txs
            ]

            tbl = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
            tbl.add_slot("no-data", _no_data_slot())

            # Pagination row
            with ui.row().classes(
                "w-full items-center justify-between px-2 pt-2 text-sm text-grey-7"
            ):
                if total == 0:
                    ui.label(t("transactions.no_results"))
                else:
                    ui.label(
                        t("transactions.showing", **{"from": start_n, "to": end_n, "total": total})
                    )

                with ui.row().classes("gap-1 items-center"):
                    ui.button(
                        icon="chevron_left", on_click=lambda: _go_page(current_page - 1)
                    ).props("flat round dense").bind_enabled_from(
                        {"v": current_page > 0},
                        "v",  # type: ignore[arg-type]
                    )
                    ui.label(
                        t("transactions.page", current=current_page + 1, total=total_pages)
                    ).classes("text-sm")
                    ui.button(
                        icon="chevron_right", on_click=lambda: _go_page(current_page + 1)
                    ).props("flat round dense").bind_enabled_from(
                        {"v": current_page < total_pages - 1},
                        "v",  # type: ignore[arg-type]
                    )

        def _go_page(page: int) -> None:
            filters["page"] = page
            transaction_table.refresh()

        def _apply_filters() -> None:
            filters["page"] = 0
            transaction_table.refresh()
            _update_badge()

        # ── Add Transaction Dialog ────────────────────────────────────────────
        # Split state (mutable containers so closures can mutate them)
        split_rows: list[dict] = []
        is_split: dict = {"value": False}

        # Build {account_id -> Account} map for currency look-ups
        accounts_by_id: dict[int, Account] = {a.id: a for a in accounts}

        dialog = ui.dialog().on("show", lambda: amount_input.run_method("focus"))
        with dialog, ui.card().classes("w-[520px]"):
            ui.label(t("transactions.add")).classes("text-lg font-bold")

            tx_type_sel = ui.select(
                {tx.value: tx.value.capitalize() for tx in TransactionType},
                label=t("common.type"),
                value=TransactionType.EXPENSE.value,
            ).classes("w-full")

            account_sel = ui.select(account_options, label=t("common.account")).classes("w-full")
            if account_options:
                account_sel.value = next(iter(account_options))

            # ── Destination account row (transfers only) ───────────────────────
            dest_row = ui.row().classes("w-full")
            dest_row.set_visibility(False)
            with dest_row:
                dest_account_sel = ui.select(
                    account_options, label=t("transactions.to_account")
                ).classes("w-full")

            # ── Exchange rate section (cross-currency transfers) ───────────────
            fx_row = ui.column().classes("w-full gap-2 border rounded p-3 bg-blue-50")
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

            # Category row (hidden in split mode and transfer mode)
            category_row = ui.row().classes("w-full")
            with category_row:
                category_sel = ui.select(expense_cats, label=t("common.category")).classes(
                    "w-full"
                )
                ui.button(
                    t("transactions.split"),
                    icon="call_split",
                    on_click=lambda: _toggle_split(),
                ).props("flat dense color=primary").tooltip(t("transactions.split_tooltip"))

            amount_input = ui.number(
                t("common.amount"), min=0.01, format="%.2f"
            ).classes("w-full").props("autofocus")
            amount_input.on_value_change(lambda _: (split_rows_ui.refresh(), _update_fx()))

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
                dest_amount_input.props(f'label="{t("transactions.dest_amount", currency=dst_cur)}"')
                fx_rate_input.props(
                    f'label="{t("transactions.exchange_rate_hint", src=src_cur, dst=dst_cur)}"'
                )
                # Auto-calculate rate when dest_amount changes
                src_amt = float(amount_input.value or 0)
                dst_amt = float(dest_amount_input.value or 0)
                rate_val = float(fx_rate_input.value or 0)
                if dst_amt > 0 and src_amt > 0 and dst_amt != rate_val * src_amt:
                    # dest_amount was just changed — recalculate rate
                    computed_rate = dst_amt / src_amt
                    fx_info.set_text(
                        t("transactions.rate_auto", src=src_cur, rate=f"{computed_rate:.6f}", dst=dst_cur)
                    )
                elif rate_val > 0 and src_amt > 0:
                    fx_info.set_text(
                        t("transactions.rate_auto", src=src_cur, rate=f"{rate_val:.6f}", dst=dst_cur)
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
                category_row.set_visibility(not is_transfer and not is_split["value"])
                _refresh_fx_visibility()

            def _refresh_fx_visibility() -> None:
                show = _is_cross_currency()
                fx_row.set_visibility(show)
                if show:
                    _update_fx()

            tx_type_sel.on("update:model-value", lambda _: on_type_change())
            account_sel.on("update:model-value", lambda _: _refresh_fx_visibility())
            dest_account_sel.on("update:model-value", lambda _: _refresh_fx_visibility())

            desc_input = ui.input(
                f"{t('common.description')} ({t('common.optional')})"
            ).classes("w-full")

            today_str = str(datetime.date.today())
            date_text = ui.input(t("common.date")).props("type=date").classes("w-full")
            date_text.value = today_str
            date_cal = ui.date(value=today_str).classes("w-full")

            def _on_text_change(e: object) -> None:
                val = getattr(e, "value", None)
                if val and val != date_cal.value:
                    try:
                        datetime.date.fromisoformat(val)
                        date_cal.set_value(val)
                    except ValueError:
                        pass

            def _on_cal_change(e: object) -> None:
                val = getattr(e, "value", None)
                if val and val != date_text.value:
                    date_text.set_value(val)

            date_text.on_value_change(_on_text_change)
            date_cal.on_value_change(_on_cal_change)

            # ── Split rows ────────────────────────────────────────────────────
            split_container = ui.column().classes("w-full gap-1 border-t pt-3 mt-1")
            split_container.set_visibility(False)

            with split_container:

                @ui.refreshable
                def split_rows_ui() -> None:
                    chosen = tx_type_sel.value
                    cats = income_cats if chosen == TransactionType.INCOME.value else expense_cats

                    for i, row in enumerate(split_rows):
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            ui.select(
                                cats,
                                label=t("common.category"),
                                value=row["category_id"],
                                on_change=lambda e, idx=i: split_rows.__setitem__(
                                    idx, {**split_rows[idx], "category_id": e.value}
                                ),
                            ).classes("flex-1 min-w-0")
                            ui.input(
                                t("common.note"),
                                value=row["note"],
                                on_change=lambda e, idx=i: split_rows.__setitem__(
                                    idx, {**split_rows[idx], "note": e.value}
                                ),
                            ).classes("w-28")
                            ui.number(
                                t("common.amount"),
                                value=row["amount"],
                                min=0.01,
                                format="%.2f",
                                on_change=lambda e, idx=i: (
                                    split_rows.__setitem__(
                                        idx, {**split_rows[idx], "amount": e.value}
                                    ),
                                    split_rows_ui.refresh(),
                                ),
                            ).classes("w-28")
                            ui.button(
                                icon="close",
                                on_click=lambda _, idx=i: _remove_split(idx),
                            ).props("flat round dense size=sm color=negative")

                    # Balance indicator + Add button
                    main_amount = Decimal(str(amount_input.value or 0))
                    total_split = sum(Decimal(str(r["amount"] or 0)) for r in split_rows)
                    remaining = main_amount - total_split
                    balanced = remaining == Decimal("0")

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
                            ui.label(t("transactions.enter_total")).classes("text-sm text-grey-5")
                        ui.button(
                            t("transactions.add_split"),
                            icon="add",
                            on_click=lambda: _add_split(),
                        ).props("flat dense size=sm color=primary")

            split_rows_ui()  # initial render creates the refreshable slot

            async def submit() -> None:
                if not account_sel.value:
                    ui.notify(t("transactions.select_account"), type="negative")
                    return
                if not amount_input.value or amount_input.value <= 0:
                    ui.notify(t("transactions.enter_amount"), type="negative")
                    return
                chosen_type = TransactionType(tx_type_sel.value)

                raw_date = date_text.value or date_cal.value
                try:
                    parsed_date = (
                        datetime.date.fromisoformat(raw_date)
                        if raw_date
                        else datetime.date.today()
                    )
                except ValueError:
                    parsed_date = datetime.date.today()

                if is_split["value"]:
                    if not split_rows:
                        ui.notify(t("transactions.add_one_split"), type="negative")
                        return
                    main_amount = Decimal(str(amount_input.value))
                    total_split = sum(Decimal(str(r["amount"] or 0)) for r in split_rows)
                    if total_split != main_amount:
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
                    )
                else:
                    if chosen_type == TransactionType.TRANSFER:
                        # ── Transfer: create both legs ─────────────────────────
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
                        async with AsyncSessionFactory() as session:
                            await TransactionService(session).create_transfer(outgoing, incoming)
                            # Persist the exchange rate for this date in the DB
                            if cross and rate and rate > 0:
                                await CurrencyRateService(session).record_transfer_rate(
                                    parsed_date, src_cur, dst_cur, rate
                                )

                        ui.notify(t("transactions.saved"), type="positive")
                        dialog.close()
                        _apply_filters()
                        return
                    else:
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
                        )

                async with AsyncSessionFactory() as session:
                    await TransactionService(session).create(data)

                ui.notify(t("transactions.saved"), type="positive")
                dialog.close()
                _apply_filters()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                ui.button(t("common.save"), on_click=submit).props("color=primary")

            ui.keyboard(
                on_key=lambda e: submit() if e.key == "Enter" and e.action.keydown else None
            )

        # Dialog helpers (defined after dialog so widget refs exist)
        def _toggle_split() -> None:
            is_split["value"] = not is_split["value"]
            is_transfer = tx_type_sel.value == TransactionType.TRANSFER.value
            category_row.set_visibility(not is_split["value"] and not is_transfer)
            split_container.set_visibility(is_split["value"])
            if is_split["value"] and not split_rows:
                split_rows.append({"category_id": None, "amount": None, "note": ""})
            split_rows_ui.refresh()

        async def _add_split() -> None:
            split_rows.append({"category_id": None, "amount": None, "note": ""})
            split_rows_ui.refresh()
            await ui.run_javascript(
                "var d=document.querySelector('.q-dialog .q-card');"
                "if(d) d.scrollTop=d.scrollHeight;"
            )

        def _remove_split(idx: int) -> None:
            split_rows.pop(idx)
            split_rows_ui.refresh()

        def _fill_last(remaining: Decimal) -> None:
            if split_rows:
                split_rows[-1] = {**split_rows[-1], "amount": float(remaining)}
            split_rows_ui.refresh()

        def _reset_dialog() -> None:
            split_rows.clear()
            is_split["value"] = False
            category_row.set_visibility(True)
            split_container.set_visibility(False)
            dest_row.set_visibility(False)
            fx_row.set_visibility(False)
            dest_account_sel.set_value(None)
            fx_rate_input.set_value(None)
            dest_amount_input.set_value(None)
            fx_info.set_text("")
            split_rows_ui.refresh()

        dialog.on("hide", lambda: _reset_dialog())

        # ── Page layout ───────────────────────────────────────────────────────
        with page_layout(t("transactions.title")):
            # Header row
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("transactions.title")).classes("text-2xl font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.label("N").classes(_KBD_CLS)
                    ui.button(
                        t("transactions.add"),
                        icon="add",
                        on_click=lambda: dialog.open(),
                    ).props("color=primary")

            # Filter card
            with ui.card().classes("w-full p-4"):
                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    ui.icon("filter_list").classes("text-grey-6")
                    ui.label(t("transactions.filters")).classes("font-medium")
                    badge_label = ui.badge("0", color="primary").classes("ml-1")
                    badge_label.set_visibility(False)
                    ui.space()
                    ui.button(
                        t("common.clear"),
                        icon="clear",
                        on_click=lambda: _clear_filters(),
                    ).props("flat dense size=sm color=grey-7")

                with ui.row().classes("w-full gap-4 flex-wrap items-end mt-2"):
                    date_from_input = (
                        ui.input(t("transactions.date_from"))
                        .props("type=date clearable")
                        .classes("w-36")
                        .on("update:model-value", lambda e: _set_date_from(e.args))
                    )
                    date_to_input = (
                        ui.input(t("transactions.date_to"))
                        .props("type=date clearable")
                        .classes("w-36")
                        .on("update:model-value", lambda e: _set_date_to(e.args))
                    )
                    account_filter = ui.select(
                        account_options,
                        label=t("transactions.accounts"),
                        multiple=True,
                        value=[],
                        on_change=lambda e: _set_list_filter("account_ids", e.value or []),
                    ).classes("w-48").props("use-chips clearable")
                    category_filter = ui.select(
                        all_cats,
                        label=t("transactions.categories"),
                        multiple=True,
                        value=[],
                        on_change=lambda e: _set_list_filter("category_ids", e.value or []),
                    ).classes("w-48").props("use-chips clearable")
                    type_filter = ui.select(
                        {tx.value: tx.value.capitalize() for tx in TransactionType},
                        label=t("transactions.types"),
                        multiple=True,
                        value=[],
                        on_change=lambda e: _set_list_filter(
                            "tx_types",
                            [TransactionType(v) for v in (e.value or [])],
                        ),
                    ).classes("w-40").props("use-chips clearable")
                    search_input = (
                        ui.input(t("transactions.search_description"))
                        .props("clearable")
                        .classes("w-52")
                        .on("update:model-value", lambda e: _set_filter("search", e.args or ""))
                    )

            # Table
            await transaction_table()

        def _update_badge() -> None:
            count = active_filter_count()
            badge_label.set_text(str(count))
            badge_label.set_visibility(count > 0)

        def _set_filter(key: str, value: object) -> None:
            filters[key] = value
            _apply_filters()

        def _set_list_filter(key: str, value: list) -> None:
            filters[key] = value
            _apply_filters()

        def _set_date_from(value: str | None) -> None:
            try:
                filters["date_from"] = datetime.date.fromisoformat(value) if value else None
            except ValueError:
                filters["date_from"] = None
            _apply_filters()

        def _set_date_to(value: str | None) -> None:
            try:
                filters["date_to"] = datetime.date.fromisoformat(value) if value else None
            except ValueError:
                filters["date_to"] = None
            _apply_filters()

        def _clear_filters() -> None:
            filters["date_from"] = None
            filters["date_to"] = None
            filters["account_ids"] = []
            filters["category_ids"] = []
            filters["tx_types"] = []
            filters["search"] = ""
            filters["page"] = 0
            date_from_input.set_value(None)
            date_to_input.set_value(None)
            account_filter.set_value([])
            category_filter.set_value([])
            type_filter.set_value([])
            search_input.set_value("")
            _update_badge()
            transaction_table.refresh()

        # ── Global keyboard shortcut: N opens dialog ──────────────────────────
        def handle_key(e: object) -> None:
            key_event = e  # type: ignore[assignment]
            no_mod = not getattr(key_event.modifiers, "ctrl", False) and not getattr(
                key_event.modifiers, "alt", False
            )
            if getattr(key_event, "key", None) == "n" and key_event.action.keydown and no_mod:
                dialog.open()

        ui.keyboard(on_key=handle_key, active=True)
