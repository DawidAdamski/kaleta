# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transactions list page — wiring, filters, table, and dialogs."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType
from kaleta.services import (
    AccountService,
    CategoryService,
    TagService,
    TransactionService,
    with_session,
)
from kaleta.views.components.filter_bar import (
    active_filter_count,
    parse_optional_date,
    render_filter_bar,
)
from kaleta.views.components.transaction_table import (
    DEFAULT_PAGE_SIZE,
    render_pagination_bar,
    render_transaction_table,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import PAGE_TITLE
from kaleta.views.transactions.add_dialog import build_add_dialog
from kaleta.views.transactions.constants import _KBD_CLS
from kaleta.views.transactions.delete_dialog import build_delete_dialog
from kaleta.views.transactions.edit_dialog import build_edit_dialog
from kaleta.views.transactions.table_actions import render_table_actions


async def transactions_page(*, open_new: bool = False) -> None:
    async def _load_reference_data(session: Any) -> tuple[Any, Any, Any]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        tags = await TagService(session).list()
        return accounts, categories, tags

    accounts, categories, tags = await with_session(_load_reference_data)

    account_options: dict[int, str] = {a.id: a.name for a in accounts}
    expense_cats = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "expense"]
    )
    income_cats = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "income"]
    )
    all_cats = CategoryService.build_option_labels(categories)
    tag_options: dict[int, str] = {tg.id: tg.name for tg in tags}
    accounts_by_id = {a.id: a for a in accounts}
    selected_tx_ids: list[int] = []

    filters: dict[str, Any] = {
        "date_from": None,
        "date_to": None,
        "account_ids": [],
        "category_ids": [],
        "tx_types": [],
        "tag_ids": [],
        "search": "",
        "page": 0,
        "page_size": DEFAULT_PAGE_SIZE,
        "grouping": "none",
    }

    def _list_or_none(key: str) -> list[Any] | None:
        return filters[key] if filters[key] else None

    table_actions_ui: Any
    filter_widgets: Any

    def _update_badge() -> None:
        count = active_filter_count(filters)
        filter_widgets.badge_label.set_text(str(count))
        filter_widgets.badge_label.set_visibility(count > 0)

    def _apply_filters() -> None:
        filters["page"] = 0
        selected_tx_ids.clear()
        transaction_table.refresh()
        table_actions_ui.refresh()
        _update_badge()

    add_dialog_ctx = build_add_dialog(
        account_options,
        accounts_by_id,
        expense_cats,
        income_cats,
        tag_options,
        on_saved=_apply_filters,
    )
    edit_dialog_ctx = build_edit_dialog(
        account_options,
        expense_cats,
        income_cats,
        tag_options,
        on_saved=_apply_filters,
    )
    _, confirm_delete_selected = build_delete_dialog(
        selected_tx_ids,
        on_deleted=_apply_filters,
    )

    @ui.refreshable
    async def transaction_table() -> None:
        page_size = filters["page_size"]
        grouping = filters["grouping"]

        async def _fetch(session: Any) -> tuple[int, Any]:
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
            return total, txs

        total, txs = await with_session(_fetch)

        total_pages = max(1, (total + page_size - 1) // page_size)
        filters["total_pages"] = total_pages
        current_page = filters["page"]
        rows = TransactionService.build_table_rows(txs, grouping)

        async def _handle_edit(e: Any) -> None:
            await edit_dialog_ctx.open_for_id(e.args)

        def _on_selection(e: object) -> None:
            selected_tx_ids.clear()
            rows_list = getattr(e, "args", None) or []
            selected_tx_ids.extend(r["id"] for r in rows_list)
            table_actions_ui.refresh()

        render_transaction_table(rows, on_edit=_handle_edit, on_selection=_on_selection)
        render_pagination_bar(
            total=total,
            current_page=current_page,
            page_size=page_size,
            total_pages=total_pages,
            grouping=grouping,
            on_grouping_change=_set_grouping,
            on_page_size_change=_set_page_size,
            on_page_change=_go_page,
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

    def _set_filter(key: str, value: object) -> None:
        filters[key] = value
        _apply_filters()

    def _set_list_filter(key: str, value: list[Any]) -> None:
        filters[key] = value
        _apply_filters()

    def _set_date_from(value: str | None) -> None:
        filters["date_from"] = parse_optional_date(value)
        _apply_filters()

    def _set_date_to(value: str | None) -> None:
        filters["date_to"] = parse_optional_date(value)
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
        filter_widgets.date_from_input.set_value(None)
        filter_widgets.date_to_input.set_value(None)
        filter_widgets.account_filter.set_value([])
        filter_widgets.category_filter.set_value([])
        filter_widgets.type_filter.set_value([])
        filter_widgets.tag_filter.set_value([])
        filter_widgets.search_input.set_value("")
        _update_badge()
        transaction_table.refresh()

    type_options = {tx.value: t(f"common.{tx.value}") for tx in TransactionType}

    with page_layout(t("transactions.title"), wide=True):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label(t("transactions.title")).classes(PAGE_TITLE)
            with ui.row().classes("gap-2 items-center"):
                ui.label("Alt+N").classes(_KBD_CLS)
                ui.button(
                    t("transactions.add"),
                    icon="add",
                    on_click=add_dialog_ctx.open,
                ).props("color=primary")

        filter_widgets = render_filter_bar(
            account_options=account_options,
            category_options=all_cats,
            type_options=type_options,
            tag_options=tag_options,
            on_date_from=_set_date_from,
            on_date_to=_set_date_to,
            on_account_change=lambda v: _set_list_filter("account_ids", v),
            on_category_change=lambda v: _set_list_filter("category_ids", v),
            on_type_change=lambda v: _set_list_filter("tx_types", [TransactionType(x) for x in v]),
            on_search_change=lambda v: _set_filter("search", v),
            on_tag_change=lambda v: _set_list_filter("tag_ids", v),
            on_clear=_clear_filters,
        )

        table_actions_ui = render_table_actions(
            selected_tx_ids,
            on_delete=confirm_delete_selected,
            refresh=lambda: table_actions_ui.refresh(),
        )

        with ui.element("div").style("overflow-x: auto; width: 100%"):
            await transaction_table()

    def handle_key(e: Any) -> None:
        if not e.action.keydown:
            return
        key = getattr(e, "key", None)
        alt_only = getattr(e.modifiers, "alt", False) and not getattr(e.modifiers, "ctrl", False)
        no_mod = not getattr(e.modifiers, "alt", False) and not getattr(e.modifiers, "ctrl", False)
        if key == "n" and alt_only:
            add_dialog_ctx.open()
        elif key == "PageDown" and no_mod:
            cur = filters["page"]
            total_pages = filters.get("total_pages", 1)
            if cur < total_pages - 1:
                _go_page(cur + 1)
        elif key == "PageUp" and no_mod:
            cur = filters["page"]
            if cur > 0:
                _go_page(cur - 1)

    ui.keyboard(on_key=handle_key, active=True)

    if open_new:
        add_dialog_ctx.open()
        await ui.run_javascript("history.replaceState(null, '', '/transactions')")
