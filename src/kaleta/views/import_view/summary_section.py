# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-import summary for the multi-file queue."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.import_view.state import QueuedFile


@dataclass
class SummarySection:
    card: ui.card
    container: ui.column
    totals_label: ui.label
    actions_row: ui.row
    start_new_btn: ui.button

    def render(self, queue: list[QueuedFile]) -> None:
        self.container.clear()
        total_imp = 0
        total_skip = 0
        total_fail = 0
        with self.container:
            for queued_file in queue:
                if queued_file.status == "done":
                    total_imp += queued_file.imported_count
                    total_skip += queued_file.skipped_dupes
                    ui.label(
                        t(
                            "import.summary_row",
                            filename=queued_file.filename,
                            imported=queued_file.imported_count,
                            skipped=queued_file.skipped_dupes,
                        )
                    ).classes("text-sm")
                    self._render_skipped_list(queued_file)
                elif queued_file.status == "failed":
                    total_fail += 1
                    ui.label(
                        t(
                            "import.summary_row_failed",
                            filename=queued_file.filename,
                            error=queued_file.status_msg or t("import.queue_status_failed"),
                        )
                    ).classes("text-sm text-red-600")
        self.totals_label.set_text(
            t(
                "import.summary_totals",
                imported=total_imp,
                skipped=total_skip,
                failed=total_fail,
            )
        )

    @staticmethod
    def _render_skipped_list(queued_file: QueuedFile) -> None:
        if not queued_file.skipped_rows:
            return
        with (
            ui.expansion(
                t("import.skipped_list_heading", count=len(queued_file.skipped_rows)),
                icon="content_copy",
            )
            .classes("w-full")
            .props("dense")
        ):
            for row in queued_file.skipped_rows:
                ui.label(
                    t(
                        "import.skipped_list_row",
                        date=row.date.isoformat(),
                        amount=f"{row.amount:.2f}",
                        description=row.description or "—",
                    )
                ).classes("text-xs text-slate-500")

    def show(self) -> None:
        self.card.set_visibility(True)

    def hide(self) -> None:
        self.card.set_visibility(False)

    def bind_start_new(self, on_click: Callable[[], None]) -> None:
        self.start_new_btn.on("click", on_click)


def build_summary_section() -> SummarySection:
    card = ui.card().classes("w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.summary_heading")).classes("text-lg font-semibold mb-2")
        container = ui.column().classes("w-full gap-1")
        totals_label = ui.label("").classes("text-sm font-semibold mt-2")
        with ui.row().classes("w-full mt-3") as actions_row:
            start_new_btn = ui.button(
                t("import.start_new"),
                icon="refresh",
            ).props("color=primary unelevated")
    return SummarySection(
        card=card,
        container=container,
        totals_label=totals_label,
        actions_row=actions_row,
        start_new_btn=start_new_btn,
    )
