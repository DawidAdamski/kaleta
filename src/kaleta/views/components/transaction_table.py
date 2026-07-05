# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared transaction table with grouping separators, tags, and pagination."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.components.amount_label import amount_cell_slot
from kaleta.views.components.empty_state import pagination_empty_label, table_no_data_slot
from kaleta.views.theme import TABLE_SURFACE

PAGE_SIZES = [25, 50, 100, 200]
DEFAULT_PAGE_SIZE = 50


def transaction_columns() -> list[dict[str, Any]]:
    """Standard column definitions for the transactions list table."""
    return [
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
            "style": (
                "max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap"
            ),
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


def _body_slot(colspan: int) -> str:
    return (
        '<tr v-if="props.row.sep_label" class="bg-slate-50">'
        f'<td colspan="{colspan}" style="font-weight:500;border-bottom:1px solid #e0e0e0"'
        ' class="text-caption text-slate-600 q-px-md q-py-xs">'
        "{{ props.row.sep_label }}"
        "</td>"
        "</tr>"
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
        f"{amount_cell_slot()}"
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
        "</q-tr>"
    )


def render_transaction_table(
    rows: list[dict[str, Any]],
    *,
    on_edit: Callable[[Any], Awaitable[None]],
    on_selection: Callable[[object], None],
    colspan: int = 9,
) -> Any:
    """Render the transactions data table and wire edit/selection events."""
    tbl = (
        ui.table(columns=transaction_columns(), rows=rows, row_key="id")
        .classes(TABLE_SURFACE)
        .style("min-width: 1100px; table-layout: fixed")
    )
    tbl.props("selection=multiple")
    tbl.add_slot("no-data", table_no_data_slot())
    tbl.add_slot("body", _body_slot(colspan))
    tbl.on("edit_tx", on_edit)
    tbl.on("update:selected", on_selection)
    return tbl


def render_pagination_bar(
    *,
    total: int,
    current_page: int,
    page_size: int,
    total_pages: int,
    grouping: str,
    on_grouping_change: Callable[[str], None],
    on_page_size_change: Callable[[int], None],
    on_page_change: Callable[[int], None],
) -> None:
    """Pagination, grouping toggle, and result count below the table."""
    start_n = current_page * page_size + 1
    end_n = min(start_n + page_size - 1, total)

    with ui.row().classes("w-full items-center justify-between px-2 pt-2 text-sm text-slate-600"):
        if total == 0:
            pagination_empty_label()
        else:
            ui.label(t("transactions.showing", **{"from": start_n, "to": end_n, "total": total}))

        with ui.row().classes("gap-3 items-center"):
            with ui.row().classes("gap-1 items-center"):
                ui.label(t("transactions.grouping")).classes("text-xs text-slate-500")
                ui.toggle(
                    {
                        "none": t("transactions.group_none"),
                        "week": t("transactions.group_week"),
                        "month": t("transactions.group_month"),
                    },
                    value=grouping,
                    on_change=lambda e: on_grouping_change(e.value),
                ).props("dense")

            ui.select(
                {s: str(s) for s in PAGE_SIZES},
                value=page_size,
                on_change=lambda e: on_page_size_change(e.value),
            ).props("dense options-dense borderless").classes("w-16 text-sm")

            with ui.row().classes("gap-1 items-center"):
                prev_btn = ui.button(
                    icon="chevron_left",
                    on_click=lambda: on_page_change(current_page - 1),
                ).props("flat round dense")
                prev_btn.bind_enabled_from({"v": current_page > 0}, "v")
                ui.label(
                    t("transactions.page", current=current_page + 1, total=total_pages)
                ).classes("text-sm")
                ui.button(
                    icon="chevron_right", on_click=lambda: on_page_change(current_page + 1)
                ).props("flat round dense").bind_enabled_from(
                    {"v": current_page < total_pages - 1},
                    "v",
                )
