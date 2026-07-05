# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard step indicator for the import page."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t


def render_step_indicator() -> None:
    steps = [
        t("import.step_format"),
        t("import.step_upload"),
        t("import.step_settings"),
        t("import.step_preview"),
        t("import.step_confirm"),
    ]
    with ui.row().classes("w-full items-center gap-0 mb-2"):
        for i, step_label in enumerate(steps):
            num = i + 1
            with ui.row().classes("items-center gap-1"):
                ui.label(str(num)).classes(
                    "text-xs font-bold rounded-full w-6 h-6 flex items-center "
                    "justify-center bg-primary text-white"
                )
                ui.label(step_label).classes("text-sm text-slate-600 font-medium")
            if i < len(steps) - 1:
                ui.label("→").classes("text-slate-400 mx-2 text-sm")
