"""CSV upload drop zone for the import wizard."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t


@dataclass
class UploadSection:
    hint_label: ui.label
    upload_widget: ui.upload

    def set_hint(self, text: str) -> None:
        self.hint_label.set_text(text)


def build_upload_section() -> UploadSection:
    with ui.card().classes("w-full"):
        ui.label(t("import.upload_section")).classes("text-lg font-semibold mb-1")
        hint_label = ui.label(t("import.upload_hint_generic")).classes("text-sm text-grey-6 mb-3")
        upload_widget = (
            ui.upload(
                label=t("import.drop_hint_generic"),
                auto_upload=True,
                multiple=True,
                max_files=20,
                max_file_size=50 * 1024 * 1024,
            )
            .props("accept=.csv flat bordered")
            .classes("w-full mt-2")
        )
    return UploadSection(hint_label=hint_label, upload_widget=upload_widget)
