# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report query as a sentence you can click through (artboard 3e).

Two drop zones and a tall filter panel said what the controls were; they
never said what the question was. The same state now reads as one line —
*Show Total Amount grouped by Category for Expense over This Year, top 10.* —
with each underlined part opening the menu that changes it. The measure and
dimension slots still accept a field dragged from the rail; clicking a rail
row does the same thing and is the shorter path.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import plural_key, t
from kaleta.views.reports.constants import (
    CHART_TYPES,
    DATE_PRESETS,
    DIMENSIONS,
    METRICS,
    TX_TYPES,
    chart_unavailable_reason,
)
from kaleta.views.reports.sentence import slot_labels
from kaleta.views.theme import (
    CHART_PICK,
    CHART_PICK_ON,
    FILTER_CHIP,
    FILTER_CHIP_EMPTY,
    MUTED,
    RAIL_EYEBROW,
    SECTION_TITLE,
    SELECTION_DIVIDER,
    SENTENCE_FOOT,
    SENTENCE_SLOT,
    SENTENCE_SLOT_EMPTY,
    SENTENCE_SLOT_TARGET,
)

#: The sentence's own size. Prose, not a form label.
_SENTENCE = "text-[15px] leading-8"


def build_config_zone(
    state: dict[str, Any],
    *,
    account_options: dict[int, str],
    category_options: dict[int, str],
    on_drop_dimension: Callable[[], None],
    on_drop_series: Callable[[], None],
    on_drop_metric: Callable[[], None],
    on_set_chart: Callable[[str], None],
    on_toggle_type: Callable[[str], None],
    on_set: Callable[[str, Any], None],
) -> Any:
    @ui.refreshable
    def config_zone() -> None:
        labels = slot_labels(state)

        def _word(text: str) -> None:
            """A connector, pulled against the slot before it when it opens with
            punctuation.

            English hangs a comma off the previous slot (", top"); Polish opens
            the same connector with a bullet ("· limit:") that wants its space.
            The rule is the first character, so neither locale needs the call
            site to know which it is.
            """
            tight = text[:1] in ",.;:!?"
            ui.label(text).classes(f"{_SENTENCE} {MUTED}" + (" -ml-1" if tight else ""))

        def _slot(
            text: str,
            *,
            drop: Callable[[], None] | None = None,
            empty: bool = False,
        ) -> Any:
            classes = f"{SENTENCE_SLOT} {_SENTENCE}"
            if drop is not None:
                classes += f" {SENTENCE_SLOT_TARGET}"
            if empty:
                classes += f" {SENTENCE_SLOT_EMPTY}"
            with ui.element("span").classes(classes) as slot:
                if drop is not None:
                    # Without preventDefault on dragover the browser refuses
                    # the drop and the slot never hears about it.
                    slot.props('ondragover="event.preventDefault()"')
                    slot.on("drop", drop)
                # An unused part of the sentence offers itself rather than
                # pointing at a menu of things to change: a plus, not a chevron.
                if empty:
                    ui.icon("add", size="15px")
                ui.label(text)
                if not empty:
                    ui.icon("expand_more", size="15px")
            return slot

        def _pick(key: str, options: list[tuple[str, ...]]) -> None:
            """A menu of the same options the rail and the old selects offered."""
            with ui.menu().props("auto-close"):
                for row in options:
                    ui.menu_item(t(row[1]), on_click=lambda k=row[0], f=key: on_set(f, k)).props(
                        "dense"
                    )

        # ── The sentence ──────────────────────────────────────────────────
        with ui.row().classes("items-center gap-x-1 gap-y-1 flex-wrap w-full"):
            _word(t("reports.sentence_show"))
            with _slot(labels.metric, drop=on_drop_metric):
                _pick("metric", list(METRICS))

            _word(t("reports.sentence_grouped_by"))
            with _slot(labels.dimension, drop=on_drop_dimension):
                _pick("dimension", list(DIMENSIONS))

            # The second dimension. Optional, and the only slot that can be
            # put back: a report with one grouping is what every saved report
            # was before this word existed.
            has_series = bool(state["series"])
            if has_series:
                _word(t("reports.series_by"))
            with (
                _slot(labels.series, drop=on_drop_series, empty=not has_series),
                ui.menu().props("auto-close"),
            ):
                ui.menu_item(t("common.none"), on_click=lambda: on_set("series", None)).props(
                    "dense"
                )
                ui.separator()
                for key, label_key, _icon in DIMENSIONS:
                    # The axis in hand is not offered as its own second axis:
                    # a report grouped by Category by Category asks nothing.
                    if key == state["dimension"]:
                        continue
                    ui.menu_item(t(label_key), on_click=lambda k=key: on_set("series", k)).props(
                        "dense"
                    )

            _word(t("reports.sentence_for"))
            with _slot(labels.types), ui.menu():
                for type_key, label_key, icon, _colour in TX_TYPES:
                    active = type_key in state["transaction_types"]
                    with (
                        ui.menu_item(on_click=lambda k=type_key: on_toggle_type(k)).props("dense"),
                        ui.row().classes("items-center gap-2 no-wrap"),
                    ):
                        ui.icon("check" if active else icon, size="16px")
                        ui.label(t(label_key))

            _word(t("reports.sentence_over"))
            with _slot(labels.period):
                _pick("date_preset", list(DATE_PRESETS))

            _word(t("reports.sentence_top"))
            with _slot(labels.top_n), ui.menu() as top_menu:
                for count in (5, 10, 20, 50, 0):
                    ui.menu_item(
                        str(count) if count else t("reports.sentence_no_limit"),
                        on_click=lambda c=count: on_set("top_n", c),
                    ).props("dense")
                ui.separator()
                # The quick values are the common ones, not the only ones:
                # the control they replace took any number from 0 to 100, and
                # 15 or 100 must stay reachable.
                with ui.row().classes("items-center gap-2 px-3 py-2 no-wrap"):
                    ui.label(t("reports.top_n")).classes(f"{MUTED} text-xs")
                    top_input = (
                        ui.number(value=int(state["top_n"] or 0), min=0, max=100, step=1)
                        .props("dense outlined")
                        .classes("w-20")
                    )
                    # Applied on Enter or on leaving the field, not on every
                    # keystroke: setting the state repaints the sentence, and
                    # a repaint mid-number would take the field away after the
                    # first digit.
                    top_input.on("keydown.enter", lambda: _set_top_n(top_input.value))
                    top_input.on("blur", lambda: _set_top_n(top_input.value))

            def _set_top_n(raw: float | None) -> None:
                value = max(0, min(100, int(raw or 0)))
                top_menu.close()
                if value != int(state["top_n"] or 0):
                    on_set("top_n", value)

            # English ends the sentence with a full stop; Polish reads as a
            # labelled line and ends with nothing, so the key may be empty.
            if end := t("reports.sentence_end"):
                _word(end)

        if state["date_preset"] == "custom":
            with ui.row().classes("gap-3 items-center"):
                ui.input(
                    t("transactions.date_from"),
                    value=state["date_from"],
                    on_change=lambda e: on_set("date_from", e.value or ""),
                ).props("type=date dense").classes("w-44")
                ui.input(
                    t("transactions.date_to"),
                    value=state["date_to"],
                    on_change=lambda e: on_set("date_to", e.value or ""),
                ).props("type=date dense").classes("w-44")

        # ── Chart type and the two list filters ───────────────────────────
        # Under one rule, labelled: artboard `3e` reads the sentence as the
        # question and this line as how it is drawn and what it leaves out.
        with ui.row().classes(f"{SENTENCE_FOOT} items-center gap-3.5 flex-wrap w-full"):
            ui.label(t("reports.chart_eyebrow")).classes(RAIL_EYEBROW)
            with ui.row().classes("items-center gap-[5px] no-wrap"):
                for chart_type, icon in CHART_TYPES:
                    active = state["chart_type"] == chart_type
                    # A type that cannot draw the query in hand says why it is
                    # out rather than drawing something wrong when clicked.
                    reason = chart_unavailable_reason(chart_type, state["series"])
                    button = (
                        ui.button(
                            icon=icon,
                            on_click=lambda c=chart_type: on_set_chart(c),
                            color=None,
                        )
                        .props("flat dense no-caps")
                        .classes(f"{CHART_PICK} {CHART_PICK_ON}" if active else CHART_PICK)
                        .tooltip(t(reason) if reason else t(f"reports.chart_{chart_type}"))
                    )
                    if reason:
                        button.props("disable")
            # 22px and the border's own tone, as the artboard draws it beside
            # 34px squares; the selection bar's 16px would read as a nick.
            ui.element("span").classes(SELECTION_DIVIDER).style(
                "height:22px;background:var(--k-border)"
            )

            if account_options:
                _list_filter(
                    state,
                    field="account_ids",
                    options=account_options,
                    empty_key="reports.filter_accounts",
                    chosen_prefix="reports.n_accounts",
                    on_set=on_set,
                )
            if category_options:
                _list_filter(
                    state,
                    field="category_ids",
                    options=category_options,
                    empty_key="reports.filter_categories",
                    chosen_prefix="reports.n_categories",
                    on_set=on_set,
                )

    return config_zone


def _list_filter(
    state: dict[str, Any],
    *,
    field: str,
    options: dict[int, str],
    empty_key: str,
    chosen_prefix: str,
    on_set: Callable[[str, Any], None],
) -> None:
    """One chip standing for a list filter: "+ Filter accounts" or "2 accounts ×".

    The chip says how many are chosen rather than naming them: the point of
    the sentence above is that the query fits on one line, and a chip that
    grew with every account chosen would undo that. It is the shared
    ``k-filter-chip`` surface (``FILTER_CHIP``) — the same one the
    transactions filter bar wears, so the two read as the same control.
    """
    chosen: list[int] = list(state[field])
    if not chosen:
        with ui.element("div").classes(f"{FILTER_CHIP} {FILTER_CHIP_EMPTY}"):
            ui.icon("add", size="14px")
            ui.label(t(empty_key))
            _options_menu(state, field=field, options=options, on_set=on_set)
        return

    # The × sits outside the chip, not inside it: the chip carries the menu,
    # and a click anywhere in it opens that menu — including on the ×.
    with ui.row().classes("items-center gap-1 no-wrap"):
        with ui.element("div").classes(FILTER_CHIP):
            # "1 account", not "1 accounts" — and Polish wants a third form
            # again at five, which is what `plural_key` is for.
            ui.label(t(plural_key(chosen_prefix, len(chosen)), count=len(chosen)))
            _options_menu(state, field=field, options=options, on_set=on_set)
        ui.icon("close", size="15px").classes(f"{MUTED} cursor-pointer").on(
            "click", lambda f=field: on_set(f, [])
        ).tooltip(t("reports.clear_filter"))


def _options_menu(
    state: dict[str, Any],
    *,
    field: str,
    options: dict[int, str],
    on_set: Callable[[str, Any], None],
) -> None:
    def _toggle(option_id: int) -> None:
        chosen = list(state[field])
        if option_id in chosen:
            chosen.remove(option_id)
        else:
            chosen.append(option_id)
        on_set(field, chosen)

    with ui.menu().classes("max-h-80"):
        ui.label(t("reports.pick_hint")).classes(f"{SECTION_TITLE} px-3 pt-2")
        for option_id, label in options.items():
            active = option_id in state[field]
            with (
                ui.menu_item(on_click=lambda i=option_id: _toggle(i)).props("dense"),
                ui.row().classes("items-center gap-2 no-wrap"),
            ):
                ui.icon("check_box" if active else "check_box_outline_blank", size="16px")
                ui.label(label)
