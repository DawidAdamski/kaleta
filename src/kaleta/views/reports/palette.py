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
from kaleta.services.saved_report_service import ReportConfig, chart_type_icon
from kaleta.views.reports.constants import DIMENSIONS, METRICS
from kaleta.views.theme import (
    ACCENT_TEXT,
    DRAGGING_BODY,
    INK,
    MUTED,
    RAIL_EYEBROW,
    RAIL_ROW,
    RAIL_ROW_ON,
    RAIL_SAVED,
    REPORT_RAIL,
)


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
        ui.label(t(title_key)).classes(f"{RAIL_EYEBROW} mb-[11px]")
        for key, label_key, _icon in rows:
            active = state[field] == key
            row = ui.row().classes(f"{RAIL_ROW} {RAIL_ROW_ON}" if active else RAIL_ROW)
            row.props("draggable=true")
            # The body class is set in the browser so the slots can light up
            # without a round trip; the server still hears the dragstart, so
            # it knows what to put in the slot when the drop lands.
            row.on(
                "dragstart",
                lambda k=key, g=drag_group: on_dragstart(k, g),
                js_handler=f"(...args) => {{ document.body.classList.add('{DRAGGING_BODY}');"
                " emit(...args) }",
            )
            row.on(
                "dragend",
                js_handler=f"() => document.body.classList.remove('{DRAGGING_BODY}')",
            )
            row.on("click", lambda k=key, f=field: on_set(f, k))
            with row:
                # The handle, not the field's own glyph: artboard `3e` says
                # "this row is draggable" seven times over and never asks the
                # reader to tell a wallet from a bank at 16px.
                ui.icon("drag_indicator", size="16px").classes(ACCENT_TEXT if active else MUTED)
                ui.label(t(label_key))

    @ui.refreshable
    async def palette_zone() -> None:
        async def _list(session: Any) -> Any:
            return await SavedReportService(session).list()

        saved = await with_session(_list)

        with ui.column().classes(f"{REPORT_RAIL} gap-[5px]"):
            _group("reports.group_by", list(DIMENSIONS), field="dimension", drag_group="dimension")
            with ui.column().classes("w-full gap-[5px] mt-6"):
                _group("reports.measure", list(METRICS), field="metric", drag_group="metric")

            if saved:
                with ui.column().classes("w-full gap-2 mt-6"):
                    ui.label(t("reports.saved")).classes(f"{RAIL_EYEBROW} mb-[3px]")
                    for report in saved:
                        # Read through the same schema the page loads it with,
                        # so the icon cannot disagree with the report it opens.
                        config = ReportConfig.from_dict(json.loads(report.config))
                        with ui.row().classes(f"{RAIL_SAVED} w-full no-wrap") as row:
                            row.on("click", lambda rid=report.id: on_load(rid))
                            ui.label(report.name).classes(f"{INK} flex-1 truncate")
                            ui.icon(chart_type_icon(config.chart_type), size="15px").classes(MUTED)
                            ui.icon("close", size="15px").classes(f"{MUTED} cursor-pointer").on(
                                "click.stop", lambda rid=report.id: on_delete(rid)
                            ).tooltip(t("common.delete"))

    return palette_zone
