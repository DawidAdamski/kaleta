from __future__ import annotations

import datetime
from decimal import Decimal

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.account import Account
from kaleta.models.category import CategoryType
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate, TransactionUpdate
from kaleta.services import AccountService, CategoryService, TagService, TransactionService
from kaleta.services.currency_rate_service import CurrencyRateService
from kaleta.views.layout import page_layout

_PAGE_SIZES = [25, 50, 100, 200]
_DEFAULT_PAGE_SIZE = 50
_KBD_CLS = "text-xs bg-grey-2 border border-grey-4 rounded px-2 py-0.5 font-mono text-grey-7"


def _build_cat_opts(cats_list: list) -> dict[int, str]:
    """Build {id: label} dict with hierarchical labels like 'Fuel → Toyota'."""
    cats_by_id = {c.id: c for c in cats_list}
    result: dict[int, str] = {}
    roots = sorted(
        [c for c in cats_list if c.parent_id is None or c.parent_id not in cats_by_id],
        key=lambda c: c.name,
    )
    for root in roots:
        result[root.id] = root.name
        children = sorted(
            [c for c in cats_list if c.parent_id == root.id], key=lambda c: c.name
        )
        for child in children:
            result[child.id] = f"{root.name} \u2192 {child.name}"
    return result


def _no_data_slot() -> str:
    return (
        f'<div class="text-center text-grey-6 py-8">{t("transactions.no_results")}</div>'
    )


def _category_label(tx: Transaction) -> str:
    if tx.is_split and tx.splits:
        names = [s.category.name for s in tx.splits if s.category]
        return f"(Split: {', '.join(names)})" if names else "(Split)"
    return tx.category.name if tx.category else "—"


def _get_sep_label(tx: Transaction, prev_tx: Transaction | None, grouping: str) -> str:
    if grouping == "none":
        return ""
    date = tx.date
    if grouping == "week":
        year, week, _ = date.isocalendar()
        label = f"W{week:02d} {year}"
        if prev_tx is None:
            return label
        py, pw, _ = prev_tx.date.isocalendar()
        return label if (year, week) != (py, pw) else ""
    # month
    label = date.strftime("%B %Y")
    if prev_tx is None:
        return label
    return label if (date.year, date.month) != (prev_tx.date.year, prev_tx.date.month) else ""


def register() -> None:
    @ui.page("/transactions")
    async def transactions_page(new: str = "") -> None:
        open_new = new == "1"
        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            categories = await CategoryService(session).list()
            tags = await TagService(session).list()

        account_options: dict[int, str] = {a.id: a.name for a in accounts}
        expense_cats: dict[int, str] = _build_cat_opts(
            [c for c in categories if c.type == CategoryType.EXPENSE]
        )
        income_cats: dict[int, str] = _build_cat_opts(
            [c for c in categories if c.type == CategoryType.INCOME]
        )
        all_cats: dict[int, str] = _build_cat_opts(categories)
        # Mutable tag dicts — updated by _reload_tags after tag management
        tag_options: dict[int, str] = {tg.id: tg.name for tg in tags}
        tag_colors: dict[int, str] = {tg.id: (tg.color or "#9E9E9E") for tg in tags}
        # Mutable list of selected transaction IDs (multi-select delete)
        selected_tx_ids: list[int] = []

        # ── Filter state ──────────────────────────────────────────────────────
        filters: dict = {
            "date_from": None,
            "date_to": None,
            "account_ids": [],
            "category_ids": [],
            "tx_types": [],
            "tag_ids": [],
            "search": "",
            "page": 0,
            "page_size": _DEFAULT_PAGE_SIZE,
            "grouping": "none",  # "none" | "week" | "month"
        }

        def active_filter_count() -> int:
            return sum(
                [
                    filters["date_from"] is not None,
                    filters["date_to"] is not None,
                    bool(filters["account_ids"]),
                    bool(filters["category_ids"]),
                    bool(filters["tx_types"]),
                    bool(filters["tag_ids"]),
                    bool(filters["search"]),
                ]
            )

        def _list_or_none(key: str) -> list | None:
            return filters[key] if filters[key] else None

        # ── Refreshable table ─────────────────────────────────────────────────
        @ui.refreshable
        async def transaction_table() -> None:
            page_size = filters["page_size"]
            grouping = filters["grouping"]

            async with AsyncSessionFactory() as session:
                svc = TransactionService(session)
                total = await svc.count(
                    account_ids=_list_or_none("account_ids"),
                    category_ids=_list_or_none("category_ids"),
                    date_from=filters["date_from"],
                    date_to=filters["date_to"],
                    tx_types=_list_or_none("tx_types"),
                    tag_ids=_list_or_none("tag_ids"),
                    search=filters["search"] or None,
                )
                txs = await svc.list(
                    account_ids=_list_or_none("account_ids"),
                    category_ids=_list_or_none("category_ids"),
                    date_from=filters["date_from"],
                    date_to=filters["date_to"],
                    tx_types=_list_or_none("tx_types"),
                    tag_ids=_list_or_none("tag_ids"),
                    search=filters["search"] or None,
                    limit=page_size,
                    offset=filters["page"] * page_size,
                )

            total_pages = max(1, (total + page_size - 1) // page_size)
            filters["total_pages"] = total_pages
            current_page = filters["page"]
            start_n = current_page * page_size + 1
            end_n = min(start_n + page_size - 1, total)

            columns = [
                {
                    "name": "date",
                    "label": t("common.date"),
                    "field": "date",
                    "sortable": True,
                    "style": "width: 95px; min-width: 95px",
                },
                {
                    "name": "account",
                    "label": t("common.account"),
                    "field": "account",
                    "align": "left",
                    "style": "width: 110px; min-width: 90px",
                },
                {
                    "name": "description",
                    "label": t("common.description"),
                    "field": "description",
                    "align": "left",
                    "style": "max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap",  # noqa: E501
                    "classes": "max-w-xs truncate",
                },
                {
                    "name": "category",
                    "label": t("common.category"),
                    "field": "category",
                    "align": "left",
                    "style": "width: 130px; min-width: 100px",
                },
                {
                    "name": "type",
                    "label": t("common.type"),
                    "field": "type",
                    "align": "left",
                    "style": "width: 80px; min-width: 70px",
                },
                {
                    "name": "amount",
                    "label": t("common.amount"),
                    "field": "amount",
                    "align": "right",
                    "sortable": True,
                    "style": "width: 110px; min-width: 90px",
                },
                {
                    "name": "tags",
                    "label": t("transactions.tags"),
                    "field": "tags",
                    "align": "left",
                    "style": "width: 100px; min-width: 80px",
                },
                {
                    "name": "actions",
                    "label": "",
                    "field": "actions",
                    "align": "right",
                    "style": "width: 48px; min-width: 48px",
                },
            ]
            rows = []
            for i, tx in enumerate(txs):
                prev_tx = txs[i - 1] if i > 0 else None
                rows.append(
                    {
                        "id": tx.id,
                        "date": str(tx.date),
                        "account": tx.account.name if tx.account else "—",
                        "description": (tx.description or "—")[:55],
                        "category": _category_label(tx),
                        "type": tx.type.value,
                        "amount": (
                            f"+{abs(tx.amount):,.2f}"
                            if tx.type == TransactionType.INCOME
                            else f"-{abs(tx.amount):,.2f}"
                        ),
                        "tags": "",  # list stored in tags_data to avoid NiceGUI list warning
                        "tags_data": [
                            {
                                "id": tg.id,
                                "name": tg.name,
                                "color": tg.color or "#9E9E9E",
                                "icon": tg.icon or "label",
                            }
                            for tg in tx.tags
                        ],
                        "sep_label": _get_sep_label(tx, prev_tx, grouping),
                    }
                )

            tbl = (
                ui.table(columns=columns, rows=rows, row_key="id")
                .classes("w-full")
                .style("min-width: 1100px; table-layout: fixed")
            )
            tbl.props("selection=multiple")
            tbl.add_slot("no-data", _no_data_slot())
            tbl.add_slot(
                "body",
                # Separator row injected before the first row of each group
                '<tr v-if="props.row.sep_label" class="bg-grey-1">'
                '<td colspan="9" style="font-weight:500;border-bottom:1px solid #e0e0e0"'
                ' class="text-caption text-grey-7 q-px-md q-py-xs">'
                "{{ props.row.sep_label }}"
                "</td>"
                "</tr>"
                # Actual data row (always rendered)
                '<q-tr :props="props">'
                "<q-td auto-width>"
                '<q-checkbox dense :model-value="props.selected"'
                ' @update:model-value="val => props.selected = val" color="primary" />'
                "</q-td>"
                '<q-td key="date" :props="props">{{ props.row.date }}</q-td>'
                '<q-td key="account" :props="props">{{ props.row.account }}</q-td>'
                '<q-td key="description" :props="props">{{ props.row.description }}</q-td>'
                '<q-td key="category" :props="props">{{ props.row.category }}</q-td>'
                '<q-td key="type" :props="props">{{ props.row.type }}</q-td>'
                '<q-td key="amount" :props="props" class="text-right">{{ props.row.amount }}</q-td>'
                '<q-td key="tags" :props="props">'
                '<q-chip v-for="tag in props.row.tags_data" :key="tag.id"'
                ' :icon="tag.icon" dense outline'
                ' :style="`border-color:${tag.color};color:${tag.color}`"'
                ' class="q-mr-xs text-xs">{{ tag.name }}</q-chip>'
                "</q-td>"
                '<q-td key="actions" :props="props" auto-width>'
                '<q-btn flat round dense icon="edit" size="sm" color="primary"'
                " @click=\"$parent.$emit('edit_tx', props.row.id)\" />"
                "</q-td>"
                "</q-tr>",
            )

            async def _handle_edit(e: object) -> None:
                await _open_edit_dialog(e.args)  # type: ignore[attr-defined]

            tbl.on("edit_tx", _handle_edit)

            def _on_selection(e: object) -> None:
                selected_tx_ids.clear()
                rows_list = getattr(e, "args", None) or []
                selected_tx_ids.extend(r["id"] for r in rows_list)
                table_actions_ui.refresh()

            tbl.on("update:selected", _on_selection)

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

                with ui.row().classes("gap-3 items-center"):
                    # Grouping selector
                    with ui.row().classes("gap-1 items-center"):
                        ui.label(t("transactions.grouping")).classes("text-xs text-grey-6")
                        ui.toggle(
                            {
                                "none": t("transactions.group_none"),
                                "week": t("transactions.group_week"),
                                "month": t("transactions.group_month"),
                            },
                            value=grouping,
                            on_change=lambda e: _set_grouping(e.value),
                        ).props("dense")

                    # Page size selector
                    ui.select(
                        {s: str(s) for s in _PAGE_SIZES},
                        value=page_size,
                        on_change=lambda e: _set_page_size(e.value),
                    ).props("dense options-dense borderless").classes("w-16 text-sm")

                    # Page navigation
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
            selected_tx_ids.clear()
            transaction_table.refresh()
            table_actions_ui.refresh()

        def _set_grouping(value: str) -> None:
            filters["grouping"] = value
            filters["page"] = 0
            transaction_table.refresh()

        def _set_page_size(value: int) -> None:
            filters["page_size"] = value
            filters["page"] = 0
            transaction_table.refresh()

        def _apply_filters() -> None:
            filters["page"] = 0
            selected_tx_ids.clear()
            transaction_table.refresh()
            table_actions_ui.refresh()
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
                {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
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

            # Tab order: amount → description → category → date → split_switch
            amount_input = ui.number(
                t("common.amount"), min=0.01, step=0.01
            ).classes("w-full").props("autofocus")
            amount_input.on_value_change(lambda _: (split_balance_ui.refresh(), _update_fx()))

            desc_input = ui.input(
                f"{t('common.description')} ({t('common.optional')})"
            ).classes("w-full")

            # Category (hidden in split mode and transfer mode)
            category_sel = ui.select(expense_cats, label=t("common.category")).classes("w-full")

            today_str = str(datetime.date.today())
            date_text = ui.input(t("common.date")).props("type=date").classes("w-full")
            date_text.value = today_str

            add_tag_sel = ui.select(
                tag_options,
                label=t("transactions.tags"),
                multiple=True,
                value=[],
            ).classes("w-full").props("use-chips clearable")

            # Split switch (hidden in transfer mode)
            split_switch = ui.switch(
                t("transactions.split"),
                on_change=lambda e: _on_split_toggle(e.value),
            )

            # ── Exchange rate section (cross-currency transfers) ───────────────
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
                        t("transactions.rate_auto",
                          src=src_cur, rate=f"{computed_rate:.6f}", dst=dst_cur)
                    )
                elif rate_val > 0 and src_amt > 0:
                    fx_info.set_text(
                        t("transactions.rate_auto",
                          src=src_cur, rate=f"{rate_val:.6f}", dst=dst_cur)
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

            # ── Split rows ────────────────────────────────────────────────────
            split_container = ui.column().classes("w-full gap-1 border-t pt-3 mt-1")
            split_container.set_visibility(False)

            with split_container:

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

                            def _on_cat_change(e, idx=i, _sel=cat_el) -> None:
                                split_rows.__setitem__(
                                    idx, {**split_rows[idx], "category_id": e.value}
                                )

                            cat_el.on_value_change(_on_cat_change)
                            ui.input(
                                t("common.note"),
                                value=row["note"],
                                on_change=lambda e, idx=i: split_rows.__setitem__(
                                    idx, {**split_rows[idx], "note": e.value}
                                ),
                            ).classes("w-28")
                            amt_el = ui.number(
                                t("common.amount"),
                                value=row["amount"],
                                min=0.01,
                                step=0.01,
                                on_change=lambda e, idx=i: (
                                    split_rows.__setitem__(
                                        idx, {**split_rows[idx], "amount": e.value}
                                    ),
                                    split_balance_ui.refresh(),
                                ),
                            ).classes("w-28")
                            if is_last:
                                # Intercept Tab on the last row's amount → add new row
                                amt_el.props('@keydown.tab.prevent="$emit(\'split_tab\')"')
                                amt_el.on("split_tab", lambda _: _handle_split_tab())
                            ui.button(
                                icon="close",
                                on_click=lambda _, idx=i: _remove_split(idx),
                            ).props("flat round dense size=sm color=negative tabindex=-1")

                @ui.refreshable
                def split_balance_ui() -> None:
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

                # Both initial renders must be inside split_container
                split_rows_ui()
                split_balance_ui()

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
                        tag_ids=add_tag_sel.value or [],
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
                            tag_ids=add_tag_sel.value or [],
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

        # ── Dialog helpers (defined after dialog so widget refs exist) ─────────

        def _on_split_toggle(value: bool) -> None:
            is_split["value"] = value
            is_transfer = tx_type_sel.value == TransactionType.TRANSFER.value
            category_sel.set_visibility(not value and not is_transfer)
            split_container.set_visibility(value)
            if value:
                # Ensure at least 2 split rows
                while len(split_rows) < 2:
                    split_rows.append({"category_id": None, "amount": None, "note": ""})
                split_rows_ui.refresh()
                split_balance_ui.refresh()
                _focus_first_split_cat()
            else:
                split_rows_ui.refresh()
                split_balance_ui.refresh()

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

        def _handle_split_tab() -> None:
            split_rows.append({"category_id": None, "amount": None, "note": ""})
            split_rows_ui.refresh()
            split_balance_ui.refresh()
            _focus_last_split_cat()

        async def _add_split() -> None:
            split_rows.append({"category_id": None, "amount": None, "note": ""})
            split_rows_ui.refresh()
            split_balance_ui.refresh()
            await ui.run_javascript(
                "var d=document.querySelector('.q-dialog .q-card');"
                "if(d) d.scrollTop=d.scrollHeight;"
            )

        def _remove_split(idx: int) -> None:
            split_rows.pop(idx)
            split_rows_ui.refresh()
            split_balance_ui.refresh()

        def _fill_last(remaining: Decimal) -> None:
            if split_rows:
                split_rows[-1] = {**split_rows[-1], "amount": float(remaining)}
            split_balance_ui.refresh()

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
            split_rows_ui.refresh()
            split_balance_ui.refresh()

        dialog.on("hide", lambda: _reset_dialog())

        # ── Edit Transaction Dialog ───────────────────────────────────────────
        edit_tx_id: dict = {"value": None}
        edit_dialog = ui.dialog()
        with edit_dialog, ui.card().classes("w-[520px]"):
            ui.label(t("transactions.edit")).classes("text-lg font-bold")

            edit_type_sel = ui.select(
                {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
                label=t("common.type"),
                value=TransactionType.EXPENSE.value,
            ).classes("w-full")

            edit_account_sel = ui.select(
                account_options, label=t("common.account")
            ).classes("w-full")

            edit_category_sel = ui.select(
                expense_cats, label=t("common.category")
            ).classes("w-full")

            edit_amount_input = ui.number(
                t("common.amount"), min=0.01, step=0.01
            ).classes("w-full")

            edit_desc_input = ui.input(
                f"{t('common.description')} ({t('common.optional')})"
            ).classes("w-full")

            edit_date_input = ui.input(t("common.date")).props("type=date").classes("w-full")

            edit_tag_sel = ui.select(
                tag_options,
                label=t("transactions.tags"),
                multiple=True,
                value=[],
            ).classes("w-full").props("use-chips clearable")

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
                        datetime.date.fromisoformat(raw_date)
                        if raw_date
                        else datetime.date.today()
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
                async with AsyncSessionFactory() as session:
                    await TransactionService(session).update(tx_id, data)
                ui.notify(t("transactions.updated"), type="positive")
                edit_dialog.close()
                _apply_filters()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=edit_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=edit_submit).props("color=primary")

        async def _open_edit_dialog(tx_id: int) -> None:
            async with AsyncSessionFactory() as session:
                tx = await TransactionService(session).get(tx_id)
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

        # ── Delete confirmation dialog ─────────────────────────────────────────
        delete_confirm_dialog = ui.dialog()
        with delete_confirm_dialog, ui.card().classes("w-[380px]"):
            delete_confirm_label = ui.label("").classes("text-base")

            async def _do_delete_selected() -> None:
                ids = list(selected_tx_ids)
                async with AsyncSessionFactory() as session:
                    svc = TransactionService(session)
                    for tx_id in ids:
                        await svc.delete(tx_id)
                delete_confirm_dialog.close()
                ui.notify(t("transactions.deleted"), type="positive")
                _apply_filters()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button(t("common.cancel"), on_click=delete_confirm_dialog.close).props("flat")
                ui.button(
                    t("common.delete"), icon="delete", on_click=_do_delete_selected
                ).props("color=negative")

        def _confirm_delete_selected() -> None:
            n = len(selected_tx_ids)
            delete_confirm_label.set_text(t("transactions.delete_confirm_multi", count=n))
            delete_confirm_dialog.open()

        async def _reload_tags() -> None:
            async with AsyncSessionFactory() as session:
                new_tags = await TagService(session).list()
            tag_options.clear()
            tag_options.update({tg.id: tg.name for tg in new_tags})
            tag_colors.clear()
            tag_colors.update({tg.id: (tg.color or "#9E9E9E") for tg in new_tags})
            add_tag_sel.set_options(tag_options)
            edit_tag_sel.set_options(tag_options)
            tag_filter_sel.set_options(tag_options)

        # ── Table actions bar (delete selected) ───────────────────────────────
        @ui.refreshable
        def table_actions_ui() -> None:
            n = len(selected_tx_ids)
            if n:
                with ui.row().classes("w-full items-center gap-2 py-1"):
                    ui.label(
                        t("transactions.delete_selected", count=n)
                    ).classes("text-sm text-grey-8 font-medium")
                    ui.button(
                        icon="delete",
                        on_click=lambda: _confirm_delete_selected(),
                    ).props("flat round dense color=negative size=sm")
                    ui.button(
                        icon="close",
                        on_click=lambda: (selected_tx_ids.clear(), table_actions_ui.refresh()),
                    ).props("flat round dense color=grey size=sm")

        # ── Page layout ───────────────────────────────────────────────────────
        with page_layout(t("transactions.title"), wide=True):
            # Header row
            with ui.row().classes("w-full items-center justify-between"):
                ui.label(t("transactions.title")).classes("text-2xl font-bold")
                with ui.row().classes("gap-2 items-center"):
                    ui.label("Alt+N").classes(_KBD_CLS)
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
                        {tx.value: t(f"common.{tx.value}") for tx in TransactionType},
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
                    tag_filter_sel = ui.select(
                        tag_options,
                        label=t("transactions.tags"),
                        multiple=True,
                        value=[],
                        on_change=lambda e: _set_list_filter("tag_ids", e.value or []),
                    ).classes("w-40").props("use-chips clearable")
                    ui.button(
                        icon="label",
                        on_click=lambda: ui.navigate.to("/tags"),
                    ).props("flat round dense color=grey-7").tooltip(t("transactions.manage_tags"))

            # Selection actions bar (visible when rows are selected)
            table_actions_ui()

            # Table (scrollable horizontally so tag chips stay on one line)
            with ui.element("div").style("overflow-x: auto; width: 100%"):
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
            filters["tag_ids"] = []
            filters["search"] = ""
            filters["page"] = 0
            date_from_input.set_value(None)
            date_to_input.set_value(None)
            account_filter.set_value([])
            category_filter.set_value([])
            type_filter.set_value([])
            tag_filter_sel.set_value([])
            search_input.set_value("")
            _update_badge()
            transaction_table.refresh()

        # ── Keyboard shortcuts: Alt+N = new tx, Page Down/Up = pagination ──
        def handle_key(e: object) -> None:
            key_event = e  # type: ignore[assignment]
            if not key_event.action.keydown:
                return
            key = getattr(key_event, "key", None)
            alt_only = getattr(key_event.modifiers, "alt", False) and not getattr(
                key_event.modifiers, "ctrl", False
            )
            no_mod = not getattr(key_event.modifiers, "alt", False) and not getattr(
                key_event.modifiers, "ctrl", False
            )
            if key == "n" and alt_only:
                dialog.open()
            elif key == "PageDown" and no_mod:
                cur = filters["page"]
                total = filters.get("total_pages", 1)
                if cur < total - 1:
                    _go_page(cur + 1)
            elif key == "PageUp" and no_mod:
                cur = filters["page"]
                if cur > 0:
                    _go_page(cur - 1)

        ui.keyboard(on_key=handle_key, active=True)

        # Auto-open dialog when navigated here via Alt+N from another page (?new=1)
        if open_new:
            dialog.open()
            await ui.run_javascript("history.replaceState(null, '', '/transactions')")
