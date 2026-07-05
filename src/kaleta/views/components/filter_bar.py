# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reusable filter toolbar for account/category/date-range/description filters."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import TOOLBAR_CARD


@dataclass
class FilterBarWidgets:
    """Handles to filter inputs — used when clearing filters from the page."""

    date_from_input: Any
    date_to_input: Any
    account_filter: Any
    category_filter: Any
    type_filter: Any
    search_input: Any
    tag_filter: Any
    badge_label: Any


def render_filter_bar(
    *,
    account_options: dict[int, str],
    category_options: dict[int, str],
    type_options: dict[str, str],
    tag_options: dict[int, str],
    on_date_from: Callable[[str | None], None],
    on_date_to: Callable[[str | None], None],
    on_account_change: Callable[[list[int]], None],
    on_category_change: Callable[[list[int]], None],
    on_type_change: Callable[[list[str]], None],
    on_search_change: Callable[[str], None],
    on_tag_change: Callable[[list[int]], None],
    on_clear: Callable[[], None],
    filters_title_key: str = "transactions.filters",
    date_from_key: str = "transactions.date_from",
    date_to_key: str = "transactions.date_to",
    accounts_key: str = "transactions.accounts",
    categories_key: str = "transactions.categories",
    types_key: str = "transactions.types",
    search_key: str = "transactions.search_description",
    tags_key: str = "transactions.tags",
    manage_tags_tooltip_key: str = "transactions.manage_tags",
) -> FilterBarWidgets:
    """Render the standard transactions filter card and return widget refs."""
    with ui.card().classes(TOOLBAR_CARD):
        with ui.row().classes("w-full items-center gap-2 flex-wrap"):
            ui.icon("filter_list").classes("k-muted text-slate-500")
            ui.label(t(filters_title_key)).classes(
                "text-sm font-semibold uppercase tracking-[0.14em] text-slate-500"
            )
            badge_label = ui.badge("0", color="primary").classes("ml-1")
            badge_label.set_visibility(False)
            ui.space()
            ui.button(t("common.clear"), icon="clear", on_click=on_clear).props(
                "flat dense size=sm color=grey-7"
            )

        with ui.row().classes("w-full gap-4 flex-wrap items-end mt-2"):
            date_from_input = (
                ui.input(t(date_from_key))
                .props("type=date clearable")
                .classes("w-36")
                .on("update:model-value", lambda e: on_date_from(e.args))
            )
            date_to_input = (
                ui.input(t(date_to_key))
                .props("type=date clearable")
                .classes("w-36")
                .on("update:model-value", lambda e: on_date_to(e.args))
            )
            account_filter = (
                ui.select(
                    account_options,
                    label=t(accounts_key),
                    multiple=True,
                    value=[],
                    on_change=lambda e: on_account_change(e.value or []),
                )
                .classes("w-48")
                .props("use-chips clearable")
            )
            category_filter = (
                ui.select(
                    category_options,
                    label=t(categories_key),
                    multiple=True,
                    value=[],
                    on_change=lambda e: on_category_change(e.value or []),
                )
                .classes("w-48")
                .props("use-chips clearable")
            )
            type_filter = (
                ui.select(
                    type_options,
                    label=t(types_key),
                    multiple=True,
                    value=[],
                    on_change=lambda e: on_type_change(e.value or []),
                )
                .classes("w-40")
                .props("use-chips clearable")
            )
            search_input = (
                ui.input(t(search_key))
                .props("clearable")
                .classes("w-52")
                .on("update:model-value", lambda e: on_search_change(e.args or ""))
            )
            tag_filter = (
                ui.select(
                    tag_options,
                    label=t(tags_key),
                    multiple=True,
                    value=[],
                    on_change=lambda e: on_tag_change(e.value or []),
                )
                .classes("w-40")
                .props("use-chips clearable")
            )
            ui.button(icon="label", on_click=lambda: ui.navigate.to("/tags")).props(
                "flat round dense color=grey-7"
            ).tooltip(t(manage_tags_tooltip_key))

    return FilterBarWidgets(
        date_from_input=date_from_input,
        date_to_input=date_to_input,
        account_filter=account_filter,
        category_filter=category_filter,
        type_filter=type_filter,
        search_input=search_input,
        tag_filter=tag_filter,
        badge_label=badge_label,
    )


def parse_optional_date(value: str | None) -> datetime.date | None:
    """Parse an ISO date string from a filter input, returning None on empty/invalid."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def active_filter_count(filters: dict[str, Any]) -> int:
    """Count how many list filters are currently active."""
    return sum(
        [
            filters.get("date_from") is not None,
            filters.get("date_to") is not None,
            bool(filters.get("account_ids")),
            bool(filters.get("category_ids")),
            bool(filters.get("tx_types")),
            bool(filters.get("tag_ids")),
            bool(filters.get("search")),
        ]
    )
