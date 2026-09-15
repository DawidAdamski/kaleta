# SPDX-License-Identifier: AGPL-3.0-or-later
"""The left rail: the fields a report can be built from (artboard 3e).

Three quiet groups under eyebrow labels — what to group by, what to measure,
and what has been saved. A row can be dragged onto its slot in the sentence,
which is the affordance the old chips had; clicking it does the same thing
and is the shorter path, so the rail is a list and not a card of chips.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import SavedReportService, with_session
from kaleta.services.saved_report_service import chart_type_icon
from kaleta.views.reports.constants import DIMENSIONS, METRICS
from kaleta.views.theme import ACCENT_TEXT, INK, MUTED, ROW_HOVER, SECTION_TITLE

#: Wide enough for the longest dimension name, narrow enough that the chart
#: beside it keeps the page.
RAIL = "w-[220px] flex-none"

_ROW = f"{ROW_HOVER} w-full items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer no-wrap"


def build_palette_zone(
    state: dict[str, Any],
    *,
    on_dragstart: Callable[[str, str], None],
    on_set: Callable[[str, Any], None],
    on_load: Callable[[int], Awaitable[None]],
    on_delete: Callable[[int], Awaitable[None]],
) -> Any:
    def _group(
        title_key: str,
        rows: list[tuple[str, str, str]],
        *,
        field: str,
        drag_group: str,
    ) -> None:
        ui.label(t(title_key)).classes(f"{SECTION_TITLE} px-2")
        for key, label_key, icon in rows:
            active = state[field] == key
            row = ui.row().classes(_ROW)
            row.props("draggable=true")
            row.on("dragstart", lambda k=key, g=drag_group: on_dragstart(k, g))
            row.on("click", lambda k=key, f=field: on_set(f, k))
            with row:
                ui.icon(icon, size="16px").classes(ACCENT_TEXT if active else MUTED)
                ui.label(t(label_key)).classes(
                    f"text-[13px] {INK} font-medium" if active else f"text-[13px] {MUTED}"
                )

    @ui.refreshable
    async def palette_zone() -> None:
        async def _list(session: Any) -> Any:
            return await SavedReportService(session).list()

        saved = await with_session(_list)

        with ui.column().classes(f"{RAIL} gap-1"):
            _group("reports.group_by", list(DIMENSIONS), field="dimension", drag_group="dimension")
            ui.space().classes("h-2")
            _group("reports.measure", list(METRICS), field="metric", drag_group="metric")

            if saved:
                ui.space().classes("h-2")
                ui.label(t("reports.saved")).classes(f"{SECTION_TITLE} px-2")
                for report in saved:
                    config = json.loads(report.config)
                    with ui.row().classes(_ROW) as row:
                        row.on("click", lambda rid=report.id: on_load(rid))
                        ui.icon(
                            chart_type_icon(str(config.get("chart_type", "bar"))), size="16px"
                        ).classes(MUTED)
                        ui.label(report.name).classes(f"text-[13px] {INK} flex-1 truncate")
                        ui.icon("close", size="15px").classes(f"{MUTED} cursor-pointer").on(
                            "click.stop", lambda rid=report.id: on_delete(rid)
                        ).tooltip(t("common.delete"))

    return palette_zone
