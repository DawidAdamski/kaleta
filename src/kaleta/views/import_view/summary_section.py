# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-import summary for the multi-file queue."""

from __future__ import annotations

from dataclasses import dataclass

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.import_view.state import QueuedFile


@dataclass
class SummarySection:
    card: ui.card
    container: ui.column
    totals_label: ui.label

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

    def show(self) -> None:
        self.card.set_visibility(True)


def build_summary_section() -> SummarySection:
    card = ui.card().classes("w-full")
    card.set_visibility(False)
    with card:
        ui.label(t("import.summary_heading")).classes("text-lg font-semibold mb-2")
        container = ui.column().classes("w-full gap-1")
        totals_label = ui.label("").classes("text-sm font-semibold mt-2")
    return SummarySection(card=card, container=container, totals_label=totals_label)
