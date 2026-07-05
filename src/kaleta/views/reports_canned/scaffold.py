# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared layout widgets for canned report pages."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.views.reports_canned.formatters import fmt
from kaleta.views.theme import PAGE_TITLE


def report_header(title: str, description: str) -> None:
    ui.label(title).classes(PAGE_TITLE)
    ui.label(description).classes("text-sm text-slate-500 -mt-2 mb-2")


def loading_label() -> None:
    ui.label(t("common.loading")).classes("text-slate-400")


def month_controls(state: dict[str, Any], on_change: Any) -> None:
    """Year+month selectors. Mutates ``state["year"]`` / ``state["month"]``."""
    today = datetime.date.today()
    years = [y for y in range(today.year - 5, today.year + 1)]
    months = {i: datetime.date(2000, i, 1).strftime("%B") for i in range(1, 13)}
    with ui.row().classes("items-end gap-3 mb-2"):
        ui.select(
            {y: str(y) for y in years},
            label=t("common.year"),
            value=state["year"],
            on_change=lambda e: (state.update(year=int(e.value)), on_change()),
        ).classes("w-32")
        ui.select(
            months,
            label=t("common.month"),
            value=state["month"],
            on_change=lambda e: (state.update(month=int(e.value)), on_change()),
        ).classes("w-40")


def kpi(title: str, value: str, icon: str, icon_color: str) -> None:
    with ui.card().classes("flex-1 min-w-44 p-4"), ui.row().classes("items-center gap-3"):
        ui.icon(icon, size="2rem").classes(f"text-{icon_color}")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-xs text-slate-500 uppercase tracking-wide")
            ui.label(value).classes("text-xl font-bold")


def render_category_table(title: str, rows_data: list[Any], colour: str) -> None:
    with ui.card().classes("flex-1 min-w-72 p-0"):
        with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
            ui.icon("label", color=colour).classes("text-xl")
            ui.label(title).classes("text-base font-semibold flex-1")
        if not rows_data:
            ui.label(t("common.none")).classes("text-slate-400 text-sm px-4 py-2")
            return
        cols = [
            {
                "name": "category",
                "label": t("common.category"),
                "field": "category",
                "align": "left",
            },
            {"name": "amount", "label": t("common.amount"), "field": "amount", "align": "right"},
        ]
        table_rows = [{"category": r.category, "amount": fmt(r.amount)} for r in rows_data]
        ui.table(columns=cols, rows=table_rows).classes("w-full").props("flat dense")


def export_button(on_click: Any) -> None:
    with ui.row().classes("justify-end w-full mt-3"):
        ui.button(t("reports_lib.export_csv"), icon="download", on_click=on_click).props(
            "outline color=primary"
        )


def date_range_controls(
    state: dict[str, Any],
    on_change: Any,
    *,
    start_key: str = "start",
    end_key: str = "end",
) -> None:
    with ui.row().classes("items-end gap-3 mb-2"):
        ui.input(
            t("transactions.date_from"),
            value=state[start_key],
            on_change=lambda e: (state.update(**{start_key: e.value}), on_change()),
        ).props("type=date").classes("w-44")
        ui.input(
            t("transactions.date_to"),
            value=state[end_key],
            on_change=lambda e: (state.update(**{end_key: e.value}), on_change()),
        ).props("type=date").classes("w-44")
