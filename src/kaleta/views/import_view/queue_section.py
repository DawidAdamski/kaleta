# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-file upload queue panel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.components.empty_state import table_no_data_slot
from kaleta.views.import_view.constants import STATUS_COLOR
from kaleta.views.import_view.state import QueuedFile


@dataclass
class QueueSection:
    container: ui.column
    import_all_btn: ui.button

    def render(
        self,
        queue: list[QueuedFile],
        active_id: str | None,
        *,
        on_select: Callable[[str], None],
        on_remove: Callable[[str], None],
    ) -> None:
        self.container.clear()
        with self.container:
            if not queue:
                ui.html(table_no_data_slot("import.queue_empty"), sanitize=False).classes("py-2")
                return
            for queued_file in queue:
                self._render_row(queued_file, active_id, on_select=on_select, on_remove=on_remove)

    def _render_row(
        self,
        queued_file: QueuedFile,
        active_id: str | None,
        *,
        on_select: Callable[[str], None],
        on_remove: Callable[[str], None],
    ) -> None:
        is_active = queued_file.id == active_id
        classes = "w-full items-center gap-3 p-2 rounded cursor-pointer border-l-4 " + (
            "border-primary" if is_active else "border-transparent"
        )
        with ui.row().classes(classes).on("click", lambda _e, fid=queued_file.id: on_select(fid)):
            colour = STATUS_COLOR.get(queued_file.status, "grey-6")
            ui.icon(
                "check_circle"
                if queued_file.status == "done"
                else "error"
                if queued_file.status == "failed"
                else "hourglass_empty"
                if queued_file.status == "importing"
                else "description",
                size="1.2rem",
            ).classes(f"text-{colour}")
            with ui.column().classes("flex-1 gap-0"):
                ui.label(queued_file.filename).classes("text-sm font-medium")
                self._subtitle(queued_file)
            ui.chip(t(f"import.queue_status_{queued_file.status}"), color=colour).props(
                "dense outline"
            )
            ui.button(
                icon="close",
                on_click=lambda _e, fid=queued_file.id: on_remove(fid),
            ).props("flat dense round color=grey-7").tooltip(t("import.queue_remove"))

    @staticmethod
    def _subtitle(queued_file: QueuedFile) -> None:
        parts: list[str] = []
        if queued_file.status == "done":
            parts.append(t("import.done", count=queued_file.imported_count))
            if queued_file.skipped_dupes:
                parts.append(t("import.skipped_dupes", count=queued_file.skipped_dupes))
        elif queued_file.status == "failed":
            parts.append(queued_file.status_msg or t("import.queue_status_failed"))
        elif queued_file.parsed_rows:
            parts.append(t("import.rows_loaded", count=len(queued_file.parsed_rows)))
        elif queued_file.status_msg:
            parts.append(queued_file.status_msg)
        if parts:
            ui.label(" · ".join(parts)).classes("text-xs text-slate-500")


def build_queue_section() -> QueueSection:
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between mb-2"):
            ui.label(t("import.queue_section")).classes("text-lg font-semibold")
            import_all_btn = ui.button(t("import.import_all"), icon="upload").props(
                "color=primary unelevated"
            )
        ui.label(t("import.queue_active_hint")).classes("text-xs text-slate-500 mb-2")
        container = ui.column().classes("w-full gap-1")
    return QueueSection(container=container, import_all_btn=import_all_btn)
