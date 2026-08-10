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


def _idx_to_widget(value: int | None) -> int:
    return _UNMAPPED if value is None else value


def _widget_to_idx(value: Any) -> int | None:
    if value is None or value == _UNMAPPED:
        return None
    return int(value)


@dataclass
class MappingSection:
    card: ui.card
    meta_label: ui.label
    sample_table: ui.table
    errors_column: ui.column
    date_sel: ui.select
    amount_sel: ui.select
    description_sel: ui.select
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
            self.meta_label.set_text(
                t(
                    "import.mapping_meta",
                    delimiter=delim,
                    columns=len(inspection.headers),
                    rows=len(inspection.sample_rows),
                )
            )
            self._render_sample(inspection)
        else:
            self.meta_label.set_text("")
            self.sample_table.rows = []

        self._render_errors(file.parse_errors)

    def mapping_from_widgets(self) -> ColumnMapping:
        return ColumnMapping(
            date=_widget_to_idx(self.date_sel.value),
            amount=_widget_to_idx(self.amount_sel.value),
            description=_widget_to_idx(self.description_sel.value),
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

    def _render_sample(self, inspection: CsvInspection) -> None:
        columns = [
            {
                "name": f"c{i}",
                "label": h.strip() or f"#{i + 1}",
                "field": f"c{i}",
                "align": "left",
            }
            for i, h in enumerate(inspection.headers)
        ]
        rows: list[dict[str, Any]] = []
        for r_idx, row in enumerate(inspection.sample_rows):
            entry: dict[str, Any] = {"idx": r_idx}
            for c_idx, _header in enumerate(inspection.headers):
                entry[f"c{c_idx}"] = row[c_idx] if c_idx < len(row) else ""
            rows.append(entry)
        self.sample_table.columns = columns
        self.sample_table.rows = rows
        self.sample_table.update()

    def _render_errors(self, errors: list[str]) -> None:
        self.errors_column.clear()
        with self.errors_column:
            for err in errors:
                ui.label(err).classes("text-sm text-negative")


def build_mapping_section() -> MappingSection:
    card = ui.card().classes("w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.mapping_section")).classes("text-lg font-semibold mb-1")
        ui.label(t("import.mapping_hint")).classes("text-xs text-slate-500 mb-2")
        meta_label = ui.label("").classes("text-xs text-slate-500 mb-2")
        sample_table = (
            ui.table(columns=[], rows=[], row_key="idx").classes("w-full mb-3").props("dense flat")
        )
        errors_column = ui.column().classes("w-full gap-1 mb-3")

        ui.label(t("import.mapping_fields")).classes("text-sm font-medium mb-1")
        with ui.row().classes("w-full gap-4 flex-wrap"):
            date_sel = ui.select({}, label=t("import.mapping_date")).classes("flex-1 min-w-48")
            amount_sel = ui.select({}, label=t("import.mapping_amount")).classes("flex-1 min-w-48")
            description_sel = ui.select({}, label=t("import.mapping_description")).classes(
                "flex-1 min-w-48"
            )
        with ui.row().classes("w-full gap-4 flex-wrap"):
            payee_sel = ui.select({}, label=t("import.mapping_payee")).classes("flex-1 min-w-48")
            counterparty_sel = ui.select({}, label=t("import.mapping_counterparty")).classes(
                "flex-1 min-w-48"
            )
            debit_sel = ui.select({}, label=t("import.mapping_debit")).classes("flex-1 min-w-48")
            credit_sel = ui.select({}, label=t("import.mapping_credit")).classes("flex-1 min-w-48")

        ui.label(t("import.mapping_formats")).classes("text-sm font-medium mb-1 mt-2")
        with ui.row().classes("w-full gap-4 flex-wrap items-center"):
            date_format_sel = ui.select(
                _DATE_FORMAT_OPTIONS, label=t("import.mapping_date_format"), value=""
            ).classes("flex-1 min-w-40")
            decimal_sel = ui.select(
                _DECIMAL_OPTIONS, label=t("import.mapping_decimal"), value=""
            ).classes("flex-1 min-w-32")
            thousands_sel = ui.select(
                _THOUSANDS_OPTIONS, label=t("import.mapping_thousands"), value=""
            ).classes("flex-1 min-w-32")
            negative_expenses_cb = ui.checkbox(t("import.mapping_negative_expenses"), value=True)

    return MappingSection(
        card=card,
        meta_label=meta_label,
        sample_table=sample_table,
        errors_column=errors_column,
        date_sel=date_sel,
        amount_sel=amount_sel,
        description_sel=description_sel,
        payee_sel=payee_sel,
        counterparty_sel=counterparty_sel,
        debit_sel=debit_sel,
        credit_sel=credit_sel,
        date_format_sel=date_format_sel,
        decimal_sel=decimal_sel,
        thousands_sel=thousands_sel,
        negative_expenses_cb=negative_expenses_cb,
    )
