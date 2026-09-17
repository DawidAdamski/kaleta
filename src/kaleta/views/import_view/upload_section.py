# SPDX-License-Identifier: AGPL-3.0-or-later
"""CSV / QIF / MT940 upload drop zone for the import wizard."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.theme import BODY_MUTED, CARD_TITLE, SECTION_CARD, UPLOADER


@dataclass
class UploadSection:
    hint_label: ui.label
    upload_widget: ui.upload

    def set_hint(self, text: str) -> None:
        self.hint_label.set_text(text)


def build_upload_section() -> UploadSection:
    with ui.card().classes(f"{SECTION_CARD} gap-0"):
        ui.label(t("import.upload_section")).classes(CARD_TITLE)
        hint_label = ui.label(t("import.upload_hint_generic")).classes(f"{BODY_MUTED} mb-3")
        upload_widget = (
            ui.upload(
                label=t("import.drop_hint_generic"),
                auto_upload=True,
                multiple=True,
                max_files=20,
                max_file_size=50 * 1024 * 1024,
            )
            # Wise downloads its MT940 as ``.mt940``; ``.940`` and ``.sta`` are
            # the other extensions the same SWIFT statement arrives under, and
            # the parser reads the content either way.
            .props("accept=.csv,.qif,.mt940,.940,.sta flat")
            .classes(f"{UPLOADER} w-full mt-2")
        )
    return UploadSection(hint_label=hint_label, upload_widget=upload_widget)
