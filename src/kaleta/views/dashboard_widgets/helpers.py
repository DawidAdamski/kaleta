# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared rendering helpers for dashboard widgets."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.views.theme import SECTION_CARD, SECTION_HEADING, SECTION_TITLE, kpi_card_classes


def fmt_amount(amount: Decimal | float | int) -> str:
    return f"{float(amount):,.2f} zł"


def kpi_card(title: str, value: str, icon: str, icon_color: str, extra_cls: str = "") -> None:
    with ui.card().classes(kpi_card_classes()), ui.row().classes("items-center gap-4 w-full"):
        with ui.element("div").classes(
            f"h-11 w-11 rounded-2xl bg-{icon_color.split('-')[0]}-500/10 "
            f"text-{icon_color.split('-')[0]}-600 flex items-center justify-center"
        ):
            ui.icon(icon, size="1.8rem")
        with ui.column().classes("gap-0"):
            ui.label(title).classes(SECTION_TITLE)
            ui.label(value).classes(f"text-2xl font-semibold tracking-tight {extra_cls}")


def section_card(title: str, *, subtitle: str | None = None) -> Any:
    card = ui.card().classes(SECTION_CARD)
    with card:
        ui.label(title).classes(SECTION_TITLE)
        if subtitle:
            ui.label(subtitle).classes(f"{SECTION_HEADING} mb-3")
    return card


def mini_stat(label: str, value: str, color: str) -> None:
    with ui.column().classes("gap-0 min-w-28"):
        ui.label(label).classes("text-xs text-grey-6 uppercase tracking-wide")
        ui.label(value).classes(f"text-lg font-semibold text-{color}")


def quick_btn(icon: str, label: str, route: str) -> None:
    ui.button(label, icon=icon, on_click=lambda r=route: ui.navigate.to(r)).props(
        "flat color=primary"
    ).classes("flex-1 min-w-40")
