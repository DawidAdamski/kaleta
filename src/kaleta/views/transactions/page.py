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
    PayeeService,
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
    attach_split_labels,
    attach_type_labels,
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
    async def _load_reference_data(session: Any) -> tuple[Any, Any, Any, Any]:
        accounts = await AccountService(session).list()
        categories = await CategoryService(session).list()
        tags = await TagService(session).list()
        payees = await PayeeService(session).list()
        return accounts, categories, tags, payees

    accounts, categories, tags, payees = await with_session(_load_reference_data)

    account_options: dict[int, str] = {a.id: a.name for a in accounts}
    expense_cats = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "expense"]
    )
    income_cats = CategoryService.build_option_labels(
        [c for c in categories if c.type.value == "income"]
    )
    all_cats = CategoryService.build_option_labels(categories)
    tag_options: dict[int, str] = {tg.id: tg.name for tg in tags}
    payee_options: dict[int, str] = {p.id: p.name for p in payees}
    accounts_by_id = {a.id: a for a in accounts}
    selected_tx_ids: list[int] = []
    #: The selected rows themselves — the bar totals the figures already on
    #: screen rather than asking the service for them again.
    selected_rows: list[dict[str, Any]] = []
    #: The live table, so the bar's "x" can untick the rows it refers to.
    table_holder: dict[str, Any] = {}
    #: This page's rows by id. The selection event arrives from the browser;
    #: the figures the bar adds up come from here, so the total is the
    #: server's own view of the page either way.
    page_rows: dict[int, dict[str, Any]] = {}

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

    def _repaint_filter_row() -> None:
        """Repaint the chips and the "Clear all N" link for the current filters."""
        count = active_filter_count(filters)
        filter_widgets.clear_all_button.set_text(t("transactions.clear_all_n", count=count))
        filter_widgets.clear_all_button.set_visibility(count > 0)
        filter_widgets.refresh_chips(filters)

    def _drop_selection() -> None:
        """Forget what was ticked, because the redraw about to happen unticks it.

        Every path that refreshes the table has to come through here: a bar
        left saying "2 selected" over a table with nothing ticked still has
        two real ids behind its delete button.
        """
        selected_tx_ids.clear()
        selected_rows.clear()

    def _untick_table() -> None:
        """Clear the checkboxes too, for the paths that keep the table standing.

        Dismissing the bar does not redraw the ledger, so the ticks have to be
        taken off the rows the user can still see — otherwise the bar is gone
        while the rows look selected, and the next tick sends all of them back.
        """
        _drop_selection()
        table = table_holder.get("table")
        if table is not None:
            table.selected = []
            table.update()

    def _apply_filters() -> None:
        filters["page"] = 0
        _drop_selection()
        transaction_table.refresh()
        table_actions_ui.refresh()
        _repaint_filter_row()

    add_dialog_ctx = build_add_dialog(
        account_options,
        accounts_by_id,
        expense_cats,
        income_cats,
        tag_options,
        payee_options,
        on_saved=_apply_filters,
    )
    edit_dialog_ctx = build_edit_dialog(
        account_options,
        expense_cats,
        income_cats,
        tag_options,
        payee_options,
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
        rows = attach_split_labels(
            attach_type_labels(TransactionService.build_table_rows(txs, grouping))
        )
        page_rows.clear()
        page_rows.update({row["id"]: row for row in rows if row.get("id") is not None})

        async def _handle_edit(e: Any) -> None:
            await edit_dialog_ctx.open_for_id(e.args)

        async def _handle_split(e: Any) -> None:
            await edit_dialog_ctx.open_for_id(e.args, arm_split=True)

        def _on_selection(e: object) -> None:
            selected_tx_ids.clear()
            selected_rows.clear()
            rows_list = getattr(e, "args", None) or []
            # The browser sends the ids; the figures come from the server's own
            # rows. An id the page no longer holds — a stale event arriving
            # after a redraw — is dropped from both, so the count, the total
            # and the delete button cannot end up describing different rows.
            selected_tx_ids.extend(r["id"] for r in rows_list if r["id"] in page_rows)
            selected_rows.extend(page_rows[tx_id] for tx_id in selected_tx_ids)
            table_actions_ui.refresh()

        table_holder["table"] = render_transaction_table(
            rows,
            on_edit=_handle_edit,
            on_split=_handle_split,
            on_selection=_on_selection,
        )
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
        _drop_selection()
        transaction_table.refresh()
        table_actions_ui.refresh()

    def _set_grouping(value: str) -> None:
        filters["grouping"] = value
        filters["page"] = 0
        _drop_selection()
        transaction_table.refresh()
        table_actions_ui.refresh()

    def _set_page_size(value: int) -> None:
        filters["page_size"] = value
        filters["page"] = 0
        _drop_selection()
        transaction_table.refresh()
        table_actions_ui.refresh()

    def _set_filter(key: str, value: object) -> None:
        filters[key] = value
        _apply_filters()

    def _set_list_filter(key: str, value: list[Any]) -> None:
        filters[key] = value
        _apply_filters()

    def _clear_dates() -> None:
        """Both ends of the date chip at once — one apply, not two."""
        filters["date_from"] = None
        filters["date_to"] = None
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
        _drop_selection()
        _repaint_filter_row()
        transaction_table.refresh()
        table_actions_ui.refresh()

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
            on_clear_dates=_clear_dates,
        )

        table_actions_ui = render_table_actions(
            selected_tx_ids,
            selected_rows,
            on_delete=confirm_delete_selected,
            on_clear=_untick_table,
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
