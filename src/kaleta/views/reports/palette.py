"""Dimension and metric palette for the report builder."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.reports.constants import DIMENSIONS, METRICS


def build_palette_zone(
    state: dict[str, Any],
    *,
    on_dragstart: Callable[[str, str], None],
) -> Any:
    @ui.refreshable
    def palette_zone() -> None:
        with ui.card().classes("p-4 w-60 flex-shrink-0"):
            ui.label(t("reports.dimensions")).classes(
                "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"
            )
            for key, label_key, icon in DIMENSIONS:
                is_active = state["dimension"] == key
                chip_cls = "cursor-grab mb-1 w-full justify-start " + (
                    "opacity-100" if is_active else "opacity-70 hover:opacity-100"
                )
                with ui.row().classes("w-full"):
                    chip = (
                        ui.chip(
                            t(label_key),
                            icon=icon,
                            color="primary" if is_active else "grey-7",
                        )
                        .classes(chip_cls)
                        .props("draggable=true")
                    )
                    chip.on("dragstart", lambda k=key: on_dragstart(k, "dimension"))
                    if is_active:
                        ui.icon("check_circle", color="primary").classes("text-base")

            ui.separator().classes("my-3")
            ui.label(t("reports.measures")).classes(
                "text-xs font-bold text-grey-6 uppercase tracking-wide mb-2"
            )
            for key, label_key, icon in METRICS:
                is_active = state["metric"] == key
                chip_cls = "cursor-grab mb-1 w-full justify-start " + (
                    "opacity-100" if is_active else "opacity-70 hover:opacity-100"
                )
                with ui.row().classes("w-full"):
                    chip = (
                        ui.chip(
                            t(label_key),
                            icon=icon,
                            color="secondary" if is_active else "grey-7",
                        )
                        .classes(chip_cls)
                        .props("draggable=true")
                    )
                    chip.on("dragstart", lambda k=key: on_dragstart(k, "metric"))
                    if is_active:
                        ui.icon("check_circle", color="secondary").classes("text-base")

    return palette_zone
