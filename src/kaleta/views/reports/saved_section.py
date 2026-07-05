# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saved reports strip at the top of the builder."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import SavedReportService, with_session
from kaleta.services.saved_report_service import chart_type_icon


def build_saved_section(
    *,
    on_load: Callable[[int], Awaitable[None]],
    on_delete: Callable[[int], Awaitable[None]],
) -> Any:
    @ui.refreshable
    async def saved_section() -> None:
        async def _list(session: Any) -> Any:
            return await SavedReportService(session).list()

        reports = await with_session(_list)
        if not reports:
            return
        ui.label(t("reports.saved")).classes("text-sm font-semibold text-grey-6 mt-4 mb-2")
        with ui.row().classes("gap-2 flex-wrap mb-2"):
            for report in reports:
                cfg_dict = json.loads(report.config)
                icon = chart_type_icon(str(cfg_dict.get("chart_type", "bar")))
                with (
                    ui.card().classes("p-2 cursor-pointer hover:shadow-md"),
                    ui.row().classes("items-center gap-1 no-wrap"),
                ):
                    ui.icon(icon, color="primary").classes("text-base")
                    ui.label(report.name).classes("text-sm font-medium")
                    ui.button(
                        icon="play_arrow",
                        on_click=lambda rid=report.id: on_load(rid),
                    ).props("flat dense round size=xs color=primary").tooltip(t("reports.run"))
                    ui.button(
                        icon="delete",
                        on_click=lambda rid=report.id: on_delete(rid),
                    ).props("flat dense round size=xs color=negative").tooltip(t("common.delete"))

    return saved_section
