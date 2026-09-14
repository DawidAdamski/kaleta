# SPDX-License-Identifier: AGPL-3.0-or-later
"""Filter toolbar for the transactions ledger — one row of chips (artboard 2a).

Each filter is a chip that shows its *value* (``01.06.2026 → 03.07.2026``,
``PKO Konto Główne +2``) and falls back to a dashed ``+ Category`` when unset,
so the toolbar says what is filtered instead of what could be. The controls
behind the chips are the same selects and inputs as before, moved into a menu:
the chips are presentation, not new filter semantics.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import FILTER_CHIP, FILTER_CHIP_EMPTY, TOOLBAR_CARD

_DATE_FMT = "%d.%m.%Y"


def format_date_range(date_from: datetime.date | None, date_to: datetime.date | None) -> str:
    """``01.06.2026 → 03.07.2026``, with one side blank when only one is set."""
    if date_from is None and date_to is None:
        return ""
    start = date_from.strftime(_DATE_FMT) if date_from else ""
    end = date_to.strftime(_DATE_FMT) if date_to else ""
    return f"{start} → {end}".strip()


def summarise_selection(names: list[str]) -> tuple[str, str]:
    """First name, plus ``+N`` for however many more are selected."""
    if not names:
        return "", ""
    rest = len(names) - 1
    return names[0], f"+{rest}" if rest else ""


def _names(ids: list[Any], options: dict[Any, str]) -> list[str]:
    return [options[i] for i in ids if i in options]


def filter_chip_label(
    field_name: str,
    filters: dict[str, Any],
    *,
    account_options: dict[int, str],
    category_options: dict[int, str],
    type_options: dict[str, str],
    tag_options: dict[int, str],
) -> tuple[str, str]:
    """What a chip reads: ``(main, extra)``, both empty when the filter is unset.

    ``extra`` is the ``+N`` tail rendered in mono beside the first name.
    """
    if field_name == "date":
        return format_date_range(filters.get("date_from"), filters.get("date_to")), ""
    if field_name == "accounts":
        return summarise_selection(_names(filters.get("account_ids") or [], account_options))
    if field_name == "categories":
        return summarise_selection(_names(filters.get("category_ids") or [], category_options))
    if field_name == "tags":
        return summarise_selection(_names(filters.get("tag_ids") or [], tag_options))
    if field_name == "types":
        values = [getattr(v, "value", v) for v in filters.get("tx_types") or []]
        return summarise_selection([type_options[v] for v in values if v in type_options])
    if field_name == "search":
        search = (filters.get("search") or "").strip()
        return (t("transactions.filter_chip_search", text=search) if search else ""), ""
    return "", ""


@dataclass
class _Chip:
    """One pill: the shell that carries the state classes, and its parts."""

    shell: ui.row
    opener: ui.row
    add_icon: ui.icon
    name_label: ui.label
    value_label: ui.label
    extra_label: ui.label
    clear_icon: ui.icon

    def open_with_keyboard(self, menu: ui.menu) -> None:
        """Let the chip be reached and opened without a mouse.

        The opener is a div, so it is not focusable and Enter does nothing to
        it — which would have locked keyboard users out of every filter the
        moment the selects moved behind the chips.
        """
        self.opener.props('tabindex="0" role="button" aria-haspopup="true"')
        # Enter is Quasar's: QMenu toggles on its anchor's keyup, and opening
        # the menu here as well would open it on keydown and close it again a
        # moment later. Space it does not handle, and ``.prevent`` stops the
        # page scrolling out from under the menu that just opened.
        self.opener.on("keydown.space.prevent", menu.open)

    def show(self, main: str, extra: str) -> None:
        """Paint the chip for a value, or fall back to the dashed empty state."""
        filled = bool(main)
        self.shell.classes(
            add=FILTER_CHIP_EMPTY if not filled else "",
            remove=FILTER_CHIP_EMPTY if filled else "",
        )
        self.add_icon.set_visibility(not filled)
        self.name_label.set_visibility(not filled)
        self.value_label.set_visibility(filled)
        self.value_label.set_text(main)
        self.extra_label.set_visibility(bool(extra))
        self.extra_label.set_text(extra)
        self.clear_icon.set_visibility(filled)


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
    #: The "Clear all N" link, whose text the page rewrites as filters change.
    clear_all_button: ui.button
    #: Repaint the chips after a filter changed. The page owns the filter dict,
    #: so only it can say when the labels went stale. Required: a default no-op
    #: would let a caller lose the repaint without anything saying so.
    refresh_chips: Callable[[dict[str, Any]], None]


def _new_chip(field_name: str, name_key: str, on_clear: Callable[[], None]) -> _Chip:
    """A pill whose ``opener`` is the element a menu hangs from to open on click."""
    with ui.row().classes(f"{FILTER_CHIP} k-chip-{field_name}") as shell:
        opener = ui.row().classes("items-center gap-1.5 no-wrap cursor-pointer")
        with opener:
            add_icon = ui.icon("add", size="15px")
            name_label = ui.label(t(name_key))
            value_label = ui.label("")
            extra_label = ui.label("").classes("k-mono k-muted text-[11px]")
        clear_icon = (
            ui.icon("close", size="15px")
            .classes("k-muted cursor-pointer")
            # Six identical "Clear" labels tell a screen-reader user nothing
            # about which filter they are on.
            .props('tabindex="0" role="button"')
            .on("click", lambda: on_clear())
            .on("keydown.enter", lambda: on_clear())
            .on("keydown.space.prevent", lambda: on_clear())
        )
        # Set as a value, not as props text: the props string is parsed, so a
        # translation holding a quote would break out of it, and Vue binds the
        # attribute verbatim — an escaped entity would be read aloud as one.
        clear_icon.props["aria-label"] = t("transactions.clear_filter", field=t(name_key))
    return _Chip(
        shell=shell,
        opener=opener,
        add_icon=add_icon,
        name_label=name_label,
        value_label=value_label,
        extra_label=extra_label,
        clear_icon=clear_icon,
    )


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
    on_clear_dates: Callable[[], None],
    filters_title_key: str = "transactions.filters",
    date_range_key: str = "transactions.date_range",
    date_from_key: str = "transactions.date_from",
    date_to_key: str = "transactions.date_to",
    accounts_key: str = "transactions.accounts",
    categories_key: str = "transactions.categories",
    types_key: str = "transactions.types",
    search_key: str = "transactions.search_description",
    tags_key: str = "transactions.tags",
    manage_tags_tooltip_key: str = "transactions.manage_tags",
) -> FilterBarWidgets:
    """Render the transactions filter chips and return widget refs."""
    chips: dict[str, _Chip] = {}
    widgets: dict[str, Any] = {}

    def _clear_date() -> None:
        # Both ends go, then the page is told once — clearing a chip should
        # cost one query, not one per field behind it.
        widgets["date_from"].set_value(None)
        widgets["date_to"].set_value(None)
        on_clear_dates()

    def _clear_select(key: str) -> Callable[[], None]:
        def _clear() -> None:
            # ``set_value`` fires the select's own ``on_change``, which is the
            # handler; calling it again here would run the filter twice.
            widgets[key].set_value([])

        return _clear

    def _clear_search() -> None:
        widgets["search"].set_value("")
        on_search_change("")

    with (
        ui.card().classes(f"{TOOLBAR_CARD} k-filter-bar"),
        ui.row().classes("w-full items-center gap-2 flex-wrap"),
    ):
        ui.icon("filter_list", size="18px").classes("k-muted")
        ui.label(t(filters_title_key)).classes("k-eyebrow mr-1")

        chips["date"] = _new_chip("date", date_range_key, _clear_date)
        with chips["date"].opener:
            date_menu = ui.menu().classes("p-3")
        with date_menu, ui.column().classes("gap-2"):
            widgets["date_from"] = (
                ui.input(t(date_from_key))
                .props("type=date clearable dense")
                .classes("w-40")
                .on("update:model-value", lambda e: on_date_from(e.args))
            )
            widgets["date_to"] = (
                ui.input(t(date_to_key))
                .props("type=date clearable dense")
                .classes("w-40")
                .on("update:model-value", lambda e: on_date_to(e.args))
            )

        chips["date"].open_with_keyboard(date_menu)

        def _select_chip(
            field_name: str,
            label_key: str,
            options: dict[Any, str],
            handler: Callable[[Any], None],
            width: str,
        ) -> ui.select:
            chip = _new_chip(field_name, label_key, _clear_select(field_name))
            chips[field_name] = chip
            with chip.opener:
                menu = ui.menu().classes("p-3")
                with menu:
                    widget = (
                        ui.select(
                            options,
                            label=t(label_key),
                            multiple=True,
                            value=[],
                            on_change=lambda e: handler(e.value or []),
                        )
                        .classes(width)
                        .props("use-chips clearable dense")
                    )
            chips[field_name].open_with_keyboard(menu)
            widgets[field_name] = widget
            return widget

        account_filter = _select_chip(
            "accounts", accounts_key, account_options, on_account_change, "w-64"
        )
        type_filter = _select_chip("types", types_key, type_options, on_type_change, "w-48")
        category_filter = _select_chip(
            "categories", categories_key, category_options, on_category_change, "w-64"
        )
        tag_filter = _select_chip("tags", tags_key, tag_options, on_tag_change, "w-48")

        chips["search"] = _new_chip("search", search_key, _clear_search)
        with chips["search"].opener:
            search_menu = ui.menu().classes("p-3")
        with search_menu:
            widgets["search"] = (
                ui.input(t(search_key))
                .props("clearable dense autofocus")
                .classes("w-64")
                .on("update:model-value", lambda e: on_search_change(e.args or ""))
            )

        chips["search"].open_with_keyboard(search_menu)

        ui.button(icon="label", on_click=lambda: ui.navigate.to("/tags")).props(
            "flat round dense size=sm color=grey-7"
        ).tooltip(t(manage_tags_tooltip_key))

        ui.space()
        clear_all_button = (
            ui.button("", on_click=lambda: on_clear())
            .props("flat dense no-caps size=sm")
            .classes("k-clear-all text-[12px] font-medium")
        )
        clear_all_button.set_visibility(False)

    def _refresh_chips(filters: dict[str, Any]) -> None:
        for field_name, chip in chips.items():
            chip.show(
                *filter_chip_label(
                    field_name,
                    filters,
                    account_options=account_options,
                    category_options=category_options,
                    type_options=type_options,
                    tag_options=tag_options,
                )
            )

    _refresh_chips({})

    return FilterBarWidgets(
        date_from_input=widgets["date_from"],
        date_to_input=widgets["date_to"],
        account_filter=account_filter,
        category_filter=category_filter,
        type_filter=type_filter,
        search_input=widgets["search"],
        tag_filter=tag_filter,
        clear_all_button=clear_all_button,
        refresh_chips=_refresh_chips,
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
    """How many filter chips are carrying a value.

    The two ends of the date range share one chip, so they count once — the
    link beside the chips says how many of them to clear.
    """
    return sum(
        [
            filters.get("date_from") is not None or filters.get("date_to") is not None,
            bool(filters.get("account_ids")),
            bool(filters.get("category_ids")),
            bool(filters.get("tx_types")),
            bool(filters.get("tag_ids")),
            bool(filters.get("search")),
        ]
    )
