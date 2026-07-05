# SPDX-License-Identifier: AGPL-3.0-or-later
"""mBank metadata banner for the active queued file."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.import_service import MBankFileMetadata


@dataclass
class MetadataSection:
    card: ui.card
    grid: ui.grid

    def render(self, metadata: MBankFileMetadata | None, row_count: int) -> None:
        if metadata is None:
            self.card.set_visibility(False)
            return
        self.grid.clear()
        with self.grid:
            for label, value in [
                (t("import.detected_client"), metadata.client_name),
                (t("import.detected_account_type"), metadata.account_type),
                (t("import.detected_currency"), metadata.currency),
                (t("import.detected_account"), metadata.account_number),
                (
                    t("import.detected_period"),
                    f"{metadata.date_from} – {metadata.date_to}"
                    if metadata.date_from and metadata.date_to
                    else "—",
                ),
                (t("import.detected_tx_count"), str(row_count)),
            ]:
                ui.label(label).classes("text-xs text-grey-6 font-medium")
                ui.label(value).classes("text-sm")
        self.card.set_visibility(True)

    def hide(self) -> None:
        self.card.set_visibility(False)


def build_metadata_section() -> MetadataSection:
    card = ui.card().classes("k-info-banner w-full bg-blue-50")
    card.set_visibility(False)
    with card:
        grid = ui.grid(columns=2).classes("w-full gap-x-6 gap-y-1")
    return MetadataSection(card=card, grid=grid)
