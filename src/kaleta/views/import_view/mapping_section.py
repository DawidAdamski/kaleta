# SPDX-License-Identifier: AGPL-3.0-or-later
"""Interactive column-mapping step for generic CSV imports."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nicegui import background_tasks, ui

from kaleta.i18n import t
from kaleta.services.import_service import ColumnMapping, CsvInspection
from kaleta.views.import_view.state import QueuedFile
from kaleta.views.theme import (
    AUTO_BADGE,
    BODY_MUTED,
    MONO,
    MUTED,
    SECTION_CARD,
    SECTION_HEADING,
    TABLE_SURFACE,
    WARNING_STRIP,
)

_UNMAPPED = -1

_DATE_FORMAT_OPTIONS: dict[str, str] = {
    "": "Auto",
    "%Y-%m-%d": "YYYY-MM-DD",
    "%d.%m.%Y": "DD.MM.YYYY",
    "%d/%m/%Y": "DD/MM/YYYY",
    "%m/%d/%Y": "MM/DD/YYYY",
    "%d-%m-%Y": "DD-MM-YYYY",
}

_DECIMAL_OPTIONS: dict[str, str] = {
    "": "Auto",
    ",": ",",
    ".": ".",
}

_THOUSANDS_OPTIONS: dict[str, str] = {
    "": "Auto",
    " ": "Space",
    ".": ".",
    ",": ",",
}


def _col_options(headers: list[str]) -> dict[int, str]:
    options: dict[int, str] = {_UNMAPPED: t("import.mapping_unmapped")}
    for i, header in enumerate(headers):
        label = header.strip() or t("import.mapping_empty_header", index=i + 1)
        options[i] = f"{i + 1}: {label}"
    return options


#: Picker name → the ``ColumnMapping`` field it maps, for the auto badges.
_DETECTABLE_FIELDS: tuple[str, ...] = (
    "date",
    "amount",
    "description",
    "payee",
    "counterparty_account",
    "debit",
    "credit",
)


def auto_detected_fields(
    detected: ColumnMapping | None, current: ColumnMapping | None
) -> frozenset[str]:
    """Which mapped columns are still the ones detection guessed.

    No new state is needed for the badge: a field is "auto" exactly while the
    picker holds the column detection chose. Change it by hand and the two
    stop matching, which is the badge going away.
    """
    if detected is None or current is None:
        return frozenset()
    return frozenset(
        name
        for name in _DETECTABLE_FIELDS
        if getattr(detected, name) is not None and getattr(detected, name) == getattr(current, name)
    )


def _idx_to_widget(value: int | None) -> int:
    return _UNMAPPED if value is None else value


def _widget_to_idx(value: Any) -> int | None:
    if value is None or value == _UNMAPPED:
        return None
    return int(value)


#: Artboard 2d shows four rows of the file. Enough to recognise a column,
#: few enough that the picker beside it stays on screen.
SAMPLE_ROWS_SHOWN = 4
#: A raw cell longer than this is cut, with the whole of it on hover.
SAMPLE_CELL_CHARS = 32
#: Row numbers spelled out in the warning before it says "and N more".
_WARNING_ROWS_LISTED = 8


def truncate_cell(value: str) -> str:
    """Shorten a raw CSV value for the sample table, keeping an ellipsis."""
    value = value.strip()
    if len(value) <= SAMPLE_CELL_CHARS:
        return value
    return value[: SAMPLE_CELL_CHARS - 1] + "…"


def sample_body_slot() -> str:
    """Vue body slot putting the whole of a cut cell behind a tooltip.

    ``c0`` holds what is shown, ``t0`` what the file actually said; the
    tooltip appears only where the two differ, so a short value does not grow
    a tooltip repeating itself.
    """
    return (
        '<q-tr :props="props">'
        '<q-td v-for="col in props.cols" :key="col.name" :props="props">'
        "{{ props.row[col.name] }}"
        "<q-tooltip v-if=\"props.row['t' + col.name.slice(1)] !== props.row[col.name]\">"
        "{{ props.row['t' + col.name.slice(1)] }}"
        "</q-tooltip>"
        "</q-td>"
        "</q-tr>"
    )


@dataclass
class MappingSection:
    card: ui.card
    meta_label: ui.label
    sample_table: ui.table
    errors_column: ui.column
    warning_strip: ui.row
    warning_label: ui.label
    badges: dict[str, ui.element]
    date_sel: ui.select
    amount_sel: ui.select
    description_sel: ui.select
    notes_sel: ui.select
    payee_sel: ui.select
    counterparty_sel: ui.select
    debit_sel: ui.select
    credit_sel: ui.select
    date_format_sel: ui.select
    decimal_sel: ui.select
    thousands_sel: ui.select
    negative_expenses_cb: ui.checkbox
    _on_change: Callable[[], Any] | None = None
    _suppress: bool = False

    def bind(self, on_change: Callable[[], Any]) -> None:
        self._on_change = on_change
        for widget in (
            self.date_sel,
            self.amount_sel,
            self.description_sel,
            self.notes_sel,
            self.payee_sel,
            self.counterparty_sel,
            self.debit_sel,
            self.credit_sel,
            self.date_format_sel,
            self.decimal_sel,
            self.thousands_sel,
            self.negative_expenses_cb,
        ):
            widget.on("update:model-value", lambda _e: self._emit())

    def _emit(self) -> None:
        if self._suppress or self._on_change is None:
            return
        result = self._on_change()
        if inspect.isawaitable(result):
            background_tasks.create(result)

    def set_visible(self, visible: bool) -> None:
        self.card.set_visibility(visible)

    def load_file(self, file: QueuedFile) -> None:
        self._suppress = True
        try:
            self._load_file_unlocked(file)
        finally:
            self._suppress = False

    def _load_file_unlocked(self, file: QueuedFile) -> None:
        inspection = file.inspection
        mapping = file.column_mapping or ColumnMapping()
        headers = inspection.headers if inspection else []
        options = _col_options(headers)

        for sel in (
            self.date_sel,
            self.amount_sel,
            self.description_sel,
            self.notes_sel,
            self.payee_sel,
            self.counterparty_sel,
            self.debit_sel,
            self.credit_sel,
        ):
            sel.options = options
            sel.update()

        self.date_sel.value = _idx_to_widget(mapping.date)
        self.amount_sel.value = _idx_to_widget(mapping.amount)
        self.description_sel.value = _idx_to_widget(mapping.description)
        self.notes_sel.value = _idx_to_widget(mapping.notes)
        self.payee_sel.value = _idx_to_widget(mapping.payee)
        self.counterparty_sel.value = _idx_to_widget(mapping.counterparty_account)
        self.debit_sel.value = _idx_to_widget(mapping.debit)
        self.credit_sel.value = _idx_to_widget(mapping.credit)
        self.date_format_sel.value = mapping.date_format
        self.decimal_sel.value = mapping.decimal_separator
        self.thousands_sel.value = mapping.thousands_separator
        self.negative_expenses_cb.value = mapping.amounts_negative_for_expenses

        if inspection is not None:
            delim = inspection.delimiter.replace("\t", "TAB")
            # "; · UTF-8 · 1 245 rows" — what the file *is*, not what the
            # table below happens to be showing of it.
            self.meta_label.set_text(
                t(
                    "import.mapping_sample_caption",
                    delimiter=delim,
                    encoding=file.encoding,
                    rows=f"{inspection.total_rows:,}".replace(",", " "),
                )
            )
            self._render_sample(inspection)
        else:
            self.meta_label.set_text("")
            self.sample_table.rows = []

        self._render_badges(inspection, mapping)
        self._render_errors(file.parse_errors, file.error_rows)

    def mapping_from_widgets(self) -> ColumnMapping:
        return ColumnMapping(
            date=_widget_to_idx(self.date_sel.value),
            amount=_widget_to_idx(self.amount_sel.value),
            description=_widget_to_idx(self.description_sel.value),
            notes=_widget_to_idx(self.notes_sel.value),
            payee=_widget_to_idx(self.payee_sel.value),
            counterparty_account=_widget_to_idx(self.counterparty_sel.value),
            debit=_widget_to_idx(self.debit_sel.value),
            credit=_widget_to_idx(self.credit_sel.value),
            date_format=str(self.date_format_sel.value or ""),
            decimal_separator=str(self.decimal_sel.value or ""),
            thousands_separator=str(self.thousands_sel.value or ""),
            amounts_negative_for_expenses=bool(self.negative_expenses_cb.value),
        )

    def sync_to_file(self, file: QueuedFile) -> None:
        file.column_mapping = self.mapping_from_widgets()

    def _render_badges(self, inspection: CsvInspection | None, mapping: ColumnMapping) -> None:
        detected = inspection.detected_mapping if inspection is not None else None
        auto = auto_detected_fields(detected, mapping)
        for name, badge in self.badges.items():
            badge.set_visibility(name in auto)

    def _render_sample(self, inspection: CsvInspection) -> None:
        # "1: Data", "2: Opis" — the same numbering the pickers use, so a
        # column in the sample and its picker name each other.
        columns = [
            {
                "name": f"c{i}",
                "label": f"{i + 1}: {h.strip()}" if h.strip() else f"{i + 1}",
                "field": f"c{i}",
                "align": "left",
            }
            for i, h in enumerate(inspection.headers)
        ]
        rows: list[dict[str, Any]] = []
        for r_idx, row in enumerate(inspection.sample_rows[:SAMPLE_ROWS_SHOWN]):
            entry: dict[str, Any] = {"idx": r_idx}
            for c_idx, _header in enumerate(inspection.headers):
                raw = row[c_idx] if c_idx < len(row) else ""
                entry[f"c{c_idx}"] = truncate_cell(raw)
                entry[f"t{c_idx}"] = raw.strip()
            rows.append(entry)
        self.sample_table.columns = columns
        self.sample_table.rows = rows
        self.sample_table.update()

    def _render_errors(self, errors: list[str], error_rows: list[int]) -> None:
        """A strip naming the rows that failed, and the messages behind it.

        The rows were only ever listed on the Preview step, which is one step
        too late: the columns that caused them are being chosen right here.
        """
        if error_rows:
            shown = ", ".join(str(n) for n in error_rows[:_WARNING_ROWS_LISTED])
            if len(error_rows) > _WARNING_ROWS_LISTED:
                shown = t(
                    "import.parse_warning_more",
                    rows=shown,
                    extra=len(error_rows) - _WARNING_ROWS_LISTED,
                )
            self.warning_label.set_text(
                t("import.parse_warning", count=len(error_rows), rows=shown)
            )
        self.warning_strip.set_visibility(bool(error_rows))

        # A message the strip already summarises is detail; a message with no
        # row behind it — "Date column is required" — is what stands between
        # the user and an import, and must not be read as a footnote.
        detail = bool(error_rows)
        self.errors_column.clear()
        with self.errors_column:
            for err in errors:
                ui.label(err).classes(f"text-xs {MUTED}" if detail else "text-sm text-negative")


def build_mapping_section() -> MappingSection:
    badges: dict[str, ui.element] = {}

    def _picker(label_key: str, field: str | None = None, *, width: str = "w-full") -> ui.select:
        """One field picker, with the ``auto`` pill that says where it came from."""
        with ui.column().classes(f"{width} gap-0.5 min-w-0"):
            select = ui.select({}, label=t(label_key)).classes("w-full")
            if field is not None:
                badge = ui.label(t("import.auto_badge")).classes(AUTO_BADGE)
                badge.set_visibility(False)
                badges[field] = badge
        return select

    card = ui.card().classes(f"{SECTION_CARD} w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.mapping_section")).classes(SECTION_HEADING)
        ui.label(t("import.mapping_hint")).classes(f"{BODY_MUTED} mb-3")

        # Two columns: the file on the left, the pickers on the right, so a
        # column is mapped while its values are on screen. Stacks under md.
        with ui.row().classes("w-full gap-6 items-start no-wrap flex-wrap md:flex-nowrap"):
            with ui.column().classes("flex-1 min-w-0 gap-2"):
                meta_label = ui.label("").classes(f"{MONO} {MUTED} text-[11px]")
                sample_table = (
                    ui.table(columns=[], rows=[], row_key="idx")
                    .classes(f"{TABLE_SURFACE} {MONO} text-[11px]")
                    .props("dense flat")
                )
                sample_table.add_slot("body", sample_body_slot())
                with ui.row().classes(
                    f"{WARNING_STRIP} w-full items-start gap-2 px-3 py-2 rounded-lg"
                ) as warning_strip:
                    ui.icon("report_problem", size="16px")
                    warning_label = ui.label("").classes("text-[12px] leading-snug")
                warning_strip.set_visibility(False)
                errors_column = ui.column().classes("w-full gap-0.5")

            with ui.column().classes("flex-1 min-w-0 gap-2"):
                ui.label(t("import.mapping_fields")).classes(f"{MUTED} k-eyebrow")
                with ui.row().classes("w-full gap-3 flex-wrap"):
                    date_sel = _picker("import.mapping_date", "date", width="flex-1 min-w-40")
                    amount_sel = _picker("import.mapping_amount", "amount", width="flex-1 min-w-40")
                description_sel = _picker("import.mapping_description", "description")
                with ui.row().classes("w-full gap-3 flex-wrap"):
                    notes_sel = _picker("import.mapping_notes", width="flex-1 min-w-40")
                    payee_sel = _picker("import.mapping_payee", "payee", width="flex-1 min-w-40")
                with ui.row().classes("w-full gap-3 flex-wrap"):
                    counterparty_sel = _picker(
                        "import.mapping_counterparty",
                        "counterparty_account",
                        width="flex-1 min-w-40",
                    )
                    debit_sel = _picker("import.mapping_debit", "debit", width="flex-1 min-w-40")
                    credit_sel = _picker("import.mapping_credit", "credit", width="flex-1 min-w-40")

                ui.label(t("import.mapping_formats")).classes(f"{MUTED} k-eyebrow mt-2")
                with ui.row().classes("w-full gap-3 flex-wrap items-center"):
                    date_format_sel = ui.select(
                        _DATE_FORMAT_OPTIONS, label=t("import.mapping_date_format"), value=""
                    ).classes("flex-1 min-w-36")
                    decimal_sel = ui.select(
                        _DECIMAL_OPTIONS, label=t("import.mapping_decimal"), value=""
                    ).classes("flex-1 min-w-28")
                    thousands_sel = ui.select(
                        _THOUSANDS_OPTIONS, label=t("import.mapping_thousands"), value=""
                    ).classes("flex-1 min-w-28")
                negative_expenses_cb = ui.checkbox(
                    t("import.mapping_negative_expenses"), value=True
                )

    return MappingSection(
        card=card,
        meta_label=meta_label,
        sample_table=sample_table,
        errors_column=errors_column,
        warning_strip=warning_strip,
        warning_label=warning_label,
        badges=badges,
        date_sel=date_sel,
        amount_sel=amount_sel,
        description_sel=description_sel,
        notes_sel=notes_sel,
        payee_sel=payee_sel,
        counterparty_sel=counterparty_sel,
        debit_sel=debit_sel,
        credit_sel=credit_sel,
        date_format_sel=date_format_sel,
        decimal_sel=decimal_sel,
        thousands_sel=thousands_sel,
        negative_expenses_cb=negative_expenses_cb,
    )
