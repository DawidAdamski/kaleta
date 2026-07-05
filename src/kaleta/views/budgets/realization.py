# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget realization tab row renderers."""

from __future__ import annotations

from nicegui import ui

from kaleta.i18n import t
from kaleta.services.budget_service import CategoryRealization
from kaleta.views.budgets.constants import STATUS_COLOUR, STATUS_LABEL_KEY
from kaleta.views.budgets.helpers import fmt_pct
from kaleta.views.components.amount_label import amount_css_class


def render_realization_row(row: CategoryRealization) -> None:
    remaining_cls = amount_css_class("expense") if row.remaining < 0 else ""
    with ui.row().classes(
        "w-full items-center gap-3 py-2 px-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800"
    ):
        with ui.column().classes("flex-[2] min-w-0 gap-0"):
            ui.label(row.category_name).classes("text-sm font-medium truncate")
            if row.parent_name:
                ui.label(row.parent_name).classes("text-xs text-slate-500")
        ui.label(f"{row.planned:,.2f}").classes("flex-1 text-sm text-right tabular-nums")
        ui.label(f"{row.actual:,.2f}").classes("flex-1 text-sm text-right tabular-nums font-medium")
        ui.label(f"{row.remaining:,.2f}").classes(
            f"flex-1 text-sm text-right tabular-nums {remaining_cls}"
        )
        ui.label(fmt_pct(row.used_pct)).classes("flex-1 text-sm text-right tabular-nums")
        ui.badge(
            t(STATUS_LABEL_KEY[row.status]),
            color=STATUS_COLOUR[row.status],
        ).props("outline").classes("w-24 justify-center")


def render_realization_header() -> None:
    with ui.row().classes(
        "w-full items-center gap-3 px-3 text-[11px] uppercase "
        "tracking-[0.08em] text-slate-500 font-semibold"
    ):
        ui.label(t("budgets.realization.col_category")).classes("flex-[2]")
        ui.label(t("budgets.realization.col_planned")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_actual")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_remaining")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_used_pct")).classes("flex-1 text-right")
        ui.label(t("budgets.realization.col_status")).classes("w-24 text-center")


def render_realization_flat(rows: list[CategoryRealization]) -> None:
    render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for row in rows:
        render_realization_row(row)


def render_realization_grouped(rows: list[CategoryRealization]) -> None:
    groups: dict[str, list[CategoryRealization]] = {}
    for row in rows:
        key = row.parent_name or row.category_name
        groups.setdefault(key, []).append(row)

    render_realization_header()
    ui.separator().classes("my-1 opacity-40")
    for group_name, group_rows in groups.items():
        with ui.row().classes("w-full items-center gap-2 mt-3"):
            ui.icon("folder", size="xs").classes("text-slate-400")
            ui.label(group_name).classes(
                "text-xs uppercase tracking-[0.12em] text-slate-500 font-semibold"
            )
        for row in group_rows:
            render_realization_row(row)
