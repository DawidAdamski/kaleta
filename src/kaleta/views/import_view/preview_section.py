"""Parsed-row preview table and type stats."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.import_service import (
    ParsedRow,
    build_preview_table_rows,
    count_row_types,
)
from kaleta.views.components.amount_label import amount_body_cell_slot
from kaleta.views.components.empty_state import table_no_data_slot


@dataclass
class PreviewSection:
    card: ui.card
    stats_row: ui.row
    preview_table: ui.table

    def render(self, rows: list[ParsedRow], known_digits: set[str]) -> None:
        counts = count_row_types(rows, known_digits)
        self.stats_row.clear()
        with self.stats_row:
            ui.chip(
                f"\U0001f4e5 {t('import.stats_expense')}: {counts.expense}",
                color="red-2",
            )
            ui.chip(
                f"\U0001f4e4 {t('import.stats_income')}: {counts.income}",
                color="green-2",
            )
            ui.chip(
                f"\U0001f504 {t('import.stats_transfer')}: {counts.transfer}",
                color="blue-2",
            )
        self.preview_table.rows = build_preview_table_rows(rows, known_digits)

    def set_visible(self, visible: bool) -> None:
        self.card.set_visibility(visible)


def build_preview_section() -> PreviewSection:
    card = ui.card().classes("w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.preview_section")).classes("text-lg font-semibold mb-1")
        ui.label(t("import.preview_hint")).classes("text-xs text-grey-6 mb-2")
        stats_row = ui.row().classes("gap-3 mb-3")
        preview_table = (
            ui.table(
                columns=[
                    {
                        "name": "date",
                        "label": t("common.date"),
                        "field": "date",
                        "align": "left",
                    },
                    {
                        "name": "amount",
                        "label": t("common.amount"),
                        "field": "amount",
                        "align": "right",
                    },
                    {
                        "name": "description",
                        "label": t("common.description"),
                        "field": "description",
                        "align": "left",
                    },
                    {
                        "name": "type",
                        "label": t("common.type"),
                        "field": "type",
                        "align": "left",
                    },
                ],
                rows=[],
                row_key="idx",
            )
            .classes("w-full")
            .props("dense")
        )
        preview_table.add_slot("body-cell-amount", amount_body_cell_slot())
        preview_table.add_slot("no-data", table_no_data_slot("import.preview_hint"))
    return PreviewSection(card=card, stats_row=stats_row, preview_table=preview_table)
