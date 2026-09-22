# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared transaction table with grouping separators, tags, and pagination."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.core.weeks import DEFAULT_WEEK_START_MODE, WeekStartMode, week_bucket
from kaleta.i18n import plural_key, t
from kaleta.views.components.amount_label import amount_cell_slot, spaced_thousands
from kaleta.views.components.empty_state import pagination_empty_label, table_no_data_slot
from kaleta.views.theme import LEDGER_FOOT, SEGMENT, SELECT_SUNKEN, TABLE_SURFACE

PAGE_SIZES = [25, 50, 100, 200]
DEFAULT_PAGE_SIZE = 50


def attach_type_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add translated ``type_label`` while keeping raw ``type`` for amount colours."""
    for row in rows:
        row_type = row.get("type")
        if isinstance(row_type, str):
            row["type_label"] = t(f"common.{row_type}")
    return rows


def attach_split_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Localise the category cell for split rows (``Split (N)`` / ``Podzielona (N)``)."""
    for row in rows:
        if row.get("has_splits"):
            count = int(row.get("split_count") or 0)
            row["category"] = t("transactions.split_category", count=count)
    return rows


def space_amounts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the figures the way artboard `2a` writes them: ``-2 400.00``.

    The strings come formatted from ``TransactionService``, which writes
    Python's comma and is read by the API as well as by this table. So the
    grouping is put right here, where the ledger is drawn, and through the
    same ``spaced_thousands`` every other restyled screen goes through —
    rather than by teaching a service what a screen's typography is.
    """
    for row in rows:
        for key in ("amount", "sep_net"):
            value = row.get(key)
            if isinstance(value, str):
                row[key] = spaced_thousands(value)
    return rows


def attach_upcoming_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Say when a planned row falls in words, next to the date it falls on.

    A date alone makes the reader count days off a calendar; "In 3 days" is
    the thing they were actually after. Built here and not in the service
    because it is a sentence, and sentences belong to the locale.
    """
    for row in rows:
        if not row.get("is_planned"):
            continue
        days = int(row.get("days_ahead") or 0)
        if days <= 0:
            row["upcoming_label"] = t("transactions.upcoming_today")
        elif days == 1:
            # "Tomorrow" beats "In 1 day", so the ``_one`` plural form of
            # ``upcoming_in_days`` is never reached from here. It stays in both
            # locales because ``plural_key`` can still return it, and a key with
            # only two of its three forms is the bug that helper exists to stop.
            row["upcoming_label"] = t("transactions.upcoming_tomorrow")
        else:
            row["upcoming_label"] = t(plural_key("transactions.upcoming_in_days", days), days=days)
    return rows


def attach_group_labels(
    rows: list[dict[str, Any]],
    grouping: str,
    week_mode: WeekStartMode = DEFAULT_WEEK_START_MODE,
) -> list[dict[str, Any]]:
    """Say what a separator separates, the way artboard `2a` words it.

    The service marks where a group starts (``W39 2026``); the band the reader
    sees names the days — "Week 39 · 29 June – 5 July 2026". Built here for the
    same reason ``attach_type_labels`` is: it is a sentence, and sentences
    belong to the locale, which a service knows nothing about.

    The week the band names is the one ``kaleta.core.weeks`` computes under the
    reader's setting — the same call the service made when it decided the row
    opened a group, so the heading and the rows under it cannot disagree.
    """
    if grouping == "none":
        return rows
    for row in rows:
        if not row.get("sep_label"):
            continue
        day = datetime.date.fromisoformat(str(row["date"]))
        if grouping == "week":
            bucket = week_bucket(day, week_mode)
            row["sep_label"] = t(
                "transactions.group_week_label",
                week=bucket.index,
                start=_day_and_month(bucket.start, bucket.start.month != bucket.end.month),
                end=_day_and_month(bucket.end, True),
            )
        else:
            row["sep_label"] = t(
                "transactions.group_month_label",
                month=t(f"payment_calendar.month_{day.month}"),
                year=day.year,
            )
    return rows


def _day_and_month(day: datetime.date, with_month: bool) -> str:
    """``29 June`` at one end of a range, ``22`` at the other when it is the same month.

    ``common.month_of_*`` and not the calendar's own month names: a month
    beside a day number is genitive in Polish (``29 czerwca``), and the
    nominative the month pickers use reads as a headline there.
    """
    if not with_month:
        return str(day.day)
    return f"{day.day} {t(f'common.month_of_{day.month}')}"


def transaction_columns() -> list[dict[str, Any]]:
    """Standard column definitions for the transactions list table."""
    return [
        {
            "name": "date",
            "label": t("common.date"),
            "field": "date",
            "sortable": True,
            # QTable right-aligns by default; the amount is the only column
            # that reads better that way.
            "align": "left",
            "style": "width: 95px; min-width: 95px",
        },
        {
            "name": "account",
            "label": t("common.account"),
            "field": "account",
            "align": "left",
            # 166px rather than the artboard's 150: its sample account is
            # "PKO Konto Główne" and a real one is "Karta Kredytowa Visa",
            # which 150 cuts two letters off. Fixed either way — an account
            # name is not allowed to set the table's width.
            "style": (
                "width: 166px; min-width: 166px; max-width: 166px;"
                " overflow: hidden; text-overflow: ellipsis"
            ),
        },
        {
            "name": "description",
            "label": t("common.description"),
            "field": "description",
            "align": "left",
            # `width:100%` is how a table with automatic layout is told which
            # column takes the slack — artboard `2a` gives description the
            # `1fr` of its grid. Without it the tags column took everything
            # (444px of a 1360px window) and pushed the row's own actions
            # 108px past the right edge, where only a sideways scroll reached
            # them.
            "style": (
                "width: 100%; min-width: 180px; overflow: hidden;"
                " text-overflow: ellipsis; white-space: nowrap"
            ),
            "classes": "max-w-xs truncate",
        },
        {
            "name": "category",
            "label": t("common.category"),
            "field": "category",
            "align": "left",
            # The artboard's 168px track, held: the pill inside truncates
            # rather than the column growing.
            "style": "width: 168px; min-width: 168px; max-width: 168px",
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
            # A fixed track, so the column cannot take the table's slack and
            # push the row's own actions off the right edge. 176px rather
            # than the artboard's 130: its rows carry one label and the
            # ledger's carry up to four, and 176 holds two side by side
            # instead of stacking each on a line of its own.
            "style": "width: 176px; min-width: 176px; max-width: 176px",
            "classes": "k-tags-cell",
        },
        {
            "name": "actions",
            "label": "",
            "field": "actions",
            "align": "right",
            "style": "width: 88px; min-width: 88px",
        },
    ]


def _body_slot(
    colspan: int,
    *,
    edit_label: str,
    split_label: str,
    notes_label: str,
    group_net_label: str,
    planned_label: str,
    planned_tooltip: str,
) -> str:
    return (
        '<tr v-if="props.row.sep_label">'
        f'<td colspan="{colspan}" class="k-sep-row q-px-md q-py-xs">'
        '<div class="row items-center justify-between no-wrap">'
        "<span>{{ props.row.sep_label }}</span>"
        '<span v-if="props.row.sep_net" class="k-mono k-muted">'
        f"<q-tooltip>{group_net_label}</q-tooltip>"
        "{{ props.row.sep_net }}"
        "</span>"
        "</div>"
        "</td>"
        "</tr>"
        # A planned row is a promise, not a record: it cannot be ticked for
        # deletion (its id belongs to no transaction), and clicking it opens
        # the plan behind it rather than a ledger editor.
        '<q-tr :props="props"'
        " :class=\"props.row.is_planned ? 'k-planned-row cursor-pointer' : ''\""
        ' @click="props.row.is_planned'
        " && $parent.$emit('open_planned', props.row.id)\">"
        "<q-td auto-width>"
        '<q-checkbox v-if="!props.row.is_planned" dense :model-value="props.selected"'
        # `info`, whose brand variable `.k-ledger-card` redefines as ink:
        # artboard `2a` ticks a row with a black box, and Quasar's colour
        # helpers are `!important` in a layer no rule of ours can outrank.
        ' @update:model-value="val => props.selected = val" color="info" />'
        "</q-td>"
        '<q-td key="date" :props="props" class="k-mono k-muted text-[12px]">'
        "{{ props.row.date_short }}"
        '<div v-if="props.row.upcoming_label" class="k-upcoming-when">'
        "{{ props.row.upcoming_label }}"
        "</div>"
        "<q-tooltip>{{ props.row.date }}</q-tooltip>"
        "</q-td>"
        '<q-td key="account" :props="props">{{ props.row.account }}</q-td>'
        '<q-td key="description" :props="props">'
        '<div class="row items-center no-wrap q-gutter-xs">'
        '<q-icon v-if="props.row.has_notes" name="sticky_note_2" size="xs" color="primary"'
        ' class="notes-row-icon"'
        f' aria-label="{notes_label}">'
        "<q-tooltip>{{ props.row.notes }}</q-tooltip>"
        "</q-icon>"
        "<span>{{ props.row.description }}</span>"
        "</div>"
        "</q-td>"
        '<q-td key="category" :props="props">'
        '<div class="row items-center no-wrap q-gutter-xs">'
        '<q-icon v-if="props.row.has_splits" name="call_split" size="xs"'
        ' class="split-row-icon">'
        "<q-tooltip>{{ props.row.split_tooltip }}</q-tooltip>"
        "</q-icon>"
        # A pill is a category's badge. A split row already has its own icon
        # and label, and a transfer or an uncategorised row has an em dash —
        # neither is a category, so neither gets a pill drawn around it.
        "<span :class=\"props.row.has_splits || props.row.category === '—'"
        " ? '' : 'k-cat-pill'\">"
        "{{ props.row.category }}"
        "</span>"
        "</div>"
        "</q-td>"
        '<q-td key="type" :props="props" class="k-muted text-[12px]">'
        "{{ props.row.type_label }}"
        "</q-td>"
        f"{amount_cell_slot()}"
        '<q-td key="tags" :props="props">'
        '<q-chip v-for="tag in props.row.tags_data" :key="tag.id"'
        ' :icon="tag.icon" dense outline'
        ' :style="`border-color:${tag.color};color:${tag.color}`"'
        ' class="q-mr-xs text-xs">{{ tag.name }}</q-chip>'
        "</q-td>"
        '<q-td key="actions" :props="props" auto-width>'
        '<q-chip v-if="props.row.is_planned" dense outline icon="schedule"'
        ' class="text-xs k-planned-chip">'
        f"{planned_label}"
        f"<q-tooltip>{planned_tooltip}</q-tooltip>"
        "</q-chip>"
        '<q-btn v-if="!props.row.is_planned" flat round dense icon="edit" size="sm"'
        # No `color`: Quasar turns `color=null` into a literal `text-null`
        # class. The tone is `.k-row-action`'s.
        ' class="k-row-action"'
        f' aria-label="{edit_label}"'
        " @click=\"$parent.$emit('edit_tx', props.row.id)\" />"
        '<q-btn v-if="!props.row.is_planned && !props.row.has_splits'
        " && props.row.type !== 'transfer'\""
        ' flat round dense icon="call_split" size="sm" class="k-row-action"'
        f' aria-label="{split_label}"'
        " @click=\"$parent.$emit('split_tx', props.row.id)\">"
        f"<q-tooltip>{split_label}</q-tooltip>"
        "</q-btn>"
        "</q-td>"
        "</q-tr>"
    )


def render_transaction_table(
    rows: list[dict[str, Any]],
    *,
    on_edit: Callable[[Any], Awaitable[None]],
    on_selection: Callable[[object], None],
    on_split: Callable[[Any], Awaitable[None]] | None = None,
    on_open_planned: Callable[[Any], Awaitable[None]] | None = None,
    colspan: int = 9,
) -> ui.table:
    """Render the transactions data table and wire edit/selection/split events."""
    tbl = (
        ui.table(columns=transaction_columns(), rows=rows, row_key="id")
        .classes(TABLE_SURFACE)
        .style("min-width: 1100px; table-layout: fixed")
    )
    tbl.props("selection=multiple hide-selected-banner")
    tbl.add_slot("no-data", table_no_data_slot())
    tbl.add_slot(
        "body",
        _body_slot(
            colspan,
            edit_label=t("common.edit"),
            split_label=t("transactions.split"),
            notes_label=t("transactions.has_notes_tooltip"),
            group_net_label=t("transactions.group_net"),
            planned_label=t("transactions.planned_chip"),
            planned_tooltip=t("transactions.planned_row_tooltip"),
        ),
    )
    tbl.on("edit_tx", on_edit)
    if on_split is not None:
        tbl.on("split_tx", on_split)
    if on_open_planned is not None:
        tbl.on("open_planned", on_open_planned)
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
    upcoming_count: int = 0,
) -> None:
    """Pagination, grouping toggle, and result count below the table.

    ``total`` counts recorded rows only — upcoming planned rows are not part
    of any page. When the filters match none of the former and some of the
    latter, "no results" would be sitting under visible rows, so the count
    says which kind the reader is looking at instead.
    """
    start_n = current_page * page_size + 1
    end_n = min(start_n + page_size - 1, total)

    # Inside the ledger card, under a rule of its own: artboard `2a` seals the
    # count, the grouping toggle and the page controls into the same box as
    # the rows they describe, rather than letting them float on the ground.
    with ui.row().classes(f"{LEDGER_FOOT} w-full items-center gap-4 text-[12.5px] k-muted"):
        if total == 0 and upcoming_count > 0:
            ui.label(
                t(
                    plural_key("transactions.upcoming_only", upcoming_count),
                    count=upcoming_count,
                )
            )
        elif total == 0:
            pagination_empty_label()
        else:
            ui.label(t("transactions.showing", **{"from": start_n, "to": end_n, "total": total}))

        ui.space()
        with ui.row().classes("gap-3 items-center"):
            with ui.row().classes("gap-2 items-center"):
                ui.label(t("transactions.grouping")).classes("k-muted text-[11.5px]")
                ui.toggle(
                    {
                        "none": t("transactions.group_none"),
                        "week": t("transactions.group_week"),
                        "month": t("transactions.group_month"),
                    },
                    value=grouping,
                    on_change=lambda e: on_grouping_change(e.value),
                ).props("dense unelevated no-caps toggle-text-color=info").classes(SEGMENT)

            ui.select(
                {s: str(s) for s in PAGE_SIZES},
                value=page_size,
                on_change=lambda e: on_page_size_change(e.value),
            ).props("dense options-dense borderless dropdown-icon=expand_more").classes(
                f"{SELECT_SUNKEN} w-[74px]"
            )

            with ui.row().classes("gap-1 items-center"):
                prev_btn = ui.button(
                    icon="chevron_left",
                    on_click=lambda: on_page_change(current_page - 1),
                ).props("flat round dense")
                prev_btn.bind_enabled_from({"v": current_page > 0}, "v")
                ui.label(
                    t("transactions.page", current=current_page + 1, total=total_pages)
                ).classes("text-[12.5px] k-ink-2")
                ui.button(
                    icon="chevron_right", on_click=lambda: on_page_change(current_page + 1)
                ).props("flat round dense").bind_enabled_from(
                    {"v": current_page < total_pages - 1},
                    "v",
                )
