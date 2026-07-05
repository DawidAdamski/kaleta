# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan annual grid — single-year and multi-year compare rendering."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import BudgetService, with_session
from kaleta.services.budget_service import AnnualPlanGrid, YearPlanSlice
from kaleta.views.budget_plan.constants import (
    INNER_MIN,
    S_ACT,
    S_CAT,
    S_MON,
    S_REC,
    S_TOT,
    month_labels,
)
from kaleta.views.budget_plan.dialogs import EditDialogs
from kaleta.views.budget_plan.helpers import (
    actual_cell_color,
    format_amount,
    plan_cell_color,
    recurring_display,
)


def build_plan_grid(
    state: dict[str, Any],
    dialogs: EditDialogs,
    *,
    on_refresh: Callable[[], None],
) -> Callable[[], Awaitable[None]]:
    """Return a refreshable async function that renders the annual plan grid."""

    @ui.refreshable
    async def plan_grid() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        selected_years = sorted(state["years"])

        async def _load(session: Any) -> AnnualPlanGrid:
            return await BudgetService(session).load_annual_plan_grid(selected_years)

        grid = await with_session(_load)

        hdr_cls = "bg-grey-9 text-grey-1" if is_dark else "bg-grey-2 text-grey-9"
        row_hover = "hover:bg-grey-9" if is_dark else "hover:bg-grey-1"
        sub_bg = "bg-grey-8" if is_dark else "bg-grey-1"
        cell_cls = "text-sm text-center py-1 px-1"
        row_cls = "items-center no-wrap gap-0 border-b"

        async def _clear_category(cat_id: int) -> None:
            async def _run(session: Any) -> None:
                await BudgetService(session).delete_all_for_category_year(
                    cat_id, state["edit_year"]
                )

            await with_session(_run)
            on_refresh()

        with (
            ui.element("div").classes("overflow-x-auto w-full rounded-lg border"),
            ui.element("div").style(INNER_MIN),
        ):
            _render_header(grid, hdr_cls=hdr_cls, row_cls=row_cls, cell_cls=cell_cls)

            if not grid.is_compare:
                slice_ = grid.slices[0]
                _render_single_year_grid(
                    slice_,
                    budget_map=slice_.budget_map,
                    dialogs=dialogs,
                    hdr_cls=hdr_cls,
                    row_hover=row_hover,
                    cell_cls=cell_cls,
                    row_cls=row_cls,
                    is_dark=is_dark,
                    clear_category=_clear_category,
                )
            else:
                _render_compare_grid(
                    grid,
                    sub_bg=sub_bg,
                    row_hover=row_hover,
                    hdr_cls=hdr_cls,
                    cell_cls=cell_cls,
                    row_cls=row_cls,
                    is_dark=is_dark,
                )

    return plan_grid


def _render_header(
    grid: AnnualPlanGrid,
    *,
    hdr_cls: str,
    row_cls: str,
    cell_cls: str,
) -> None:
    with ui.row().classes(f"{row_cls} {hdr_cls} font-bold"):
        ui.label(t("common.category")).classes("text-sm font-bold px-3 py-2").style(S_CAT)
        if not grid.is_compare:
            ui.label(t("common.month")).classes(f"{cell_cls} font-bold").style(S_REC)
        else:
            ui.label(t("common.year")).classes(f"{cell_cls} font-bold").style(S_REC)
        for month_lbl in month_labels():
            ui.label(month_lbl).classes(f"{cell_cls} font-bold").style(S_MON)
        ui.label(t("budget_plan.year_total")).classes(
            "text-sm font-bold px-3 py-2 text-right"
        ).style(S_TOT)
        if not grid.is_compare:
            ui.label(t("common.actions")).classes("text-sm font-bold px-3 py-2").style(S_ACT)


def _render_single_year_grid(
    slice_: YearPlanSlice,
    *,
    budget_map: dict[tuple[int, int], Decimal],
    dialogs: EditDialogs,
    hdr_cls: str,
    row_hover: str,
    cell_cls: str,
    row_cls: str,
    is_dark: bool,
    clear_category: Callable[[int], Awaitable[None]],
) -> None:
    act_bg = "bg-grey-8" if is_dark else "bg-grey-1"

    for row in slice_.rows:
        rec_text, rec_color = recurring_display(row)
        name_suffix = " text-grey-6 pl-7" if row.is_child else " font-medium"
        name_cls = "text-sm px-3 py-2 truncate" + name_suffix

        with ui.row().classes(f"{row_cls} {row_hover}"):
            with (
                ui.element("div")
                .style(S_CAT)
                .classes("flex items-center gap-1 py-1 overflow-hidden")
            ):
                if row.is_child:
                    ui.icon("subdirectory_arrow_right").classes(
                        "text-grey-5 ml-2 text-sm flex-shrink-0"
                    )
                ui.label(row.name).classes(name_cls).style(
                    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                )

            suggest = float(row.uniform_monthly) if row.uniform_monthly else 0.0
            (
                ui.label(rec_text)
                .classes(f"{cell_cls} font-medium {rec_color} cursor-pointer")
                .style(S_REC)
                .on(
                    "click",
                    lambda r=row, s=suggest: dialogs.open_monthly(
                        cat_id=r.category_id, cat_name=r.name, suggest=s
                    ),
                )
            )

            for cell in row.months:
                color = plan_cell_color(cell.planned, cell.is_override)
                (
                    ui.label(format_amount(cell.planned))
                    .classes(f"{cell_cls} cursor-pointer hover:bg-blue-1 rounded {color}")
                    .style(S_MON)
                    .on(
                        "click",
                        lambda r=row, c=cell: dialogs.open_cell(
                            cat_id=r.category_id,
                            month=c.month,
                            cat_name=r.name,
                            current=c.planned,
                        ),
                    )
                )

            ui.label(format_amount(row.total_planned or None)).classes(
                "text-sm text-right px-3 py-2 font-medium"
            ).style(S_TOT)

            with ui.row().classes("gap-0 px-1 items-center").style(S_ACT):
                ui.button(
                    icon="event_note",
                    on_click=lambda r=row: dialogs.open_yearly(
                        cat_id=r.category_id,
                        cat_name=r.name,
                        budget_map=budget_map,
                    ),
                ).props("flat round dense size=sm color=orange-8").tooltip(
                    t("budget_plan.set_from_yearly")
                )
                ui.button(
                    icon="delete_sweep",
                    on_click=lambda r=row: clear_category(r.category_id),
                ).props("flat round dense size=sm color=negative").tooltip(
                    t("budget_plan.clear_all")
                )

        if row.show_actual_row:
            with ui.row().classes(f"items-center no-wrap gap-0 {act_bg}"):
                ui.label(t("budget_plan.actual")).classes(
                    "text-xs text-grey-5 italic px-3 py-0"
                ).style(S_CAT)
                ui.label("").style(S_REC)
                for cell in row.months:
                    act_color = actual_cell_color(cell.actual, cell.is_over_budget)
                    ui.label(format_amount(cell.actual)).classes(
                        f"text-xs text-center py-0 px-1 {act_color}"
                    ).style(S_MON)
                ui.label(format_amount(row.total_actual or None)).classes(
                    "text-xs text-right px-3 py-0 text-grey-6"
                ).style(S_TOT)
                ui.label("").style(S_ACT)

    with ui.row().classes(f"{row_cls} {hdr_cls} font-bold border-t-2"):
        ui.label(t("budget_plan.planned")).classes("text-sm font-bold px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        for tot in slice_.month_planned_totals:
            ui.label(format_amount(tot or None)).classes(f"{cell_cls} font-bold").style(S_MON)
        ui.label(format_amount(slice_.grand_planned or None)).classes(
            "text-sm font-bold text-right px-3 py-2"
        ).style(S_TOT)
        ui.label("").style(S_ACT)

    with ui.row().classes(f"{row_cls} {hdr_cls} border-t"):
        ui.label(t("budget_plan.actual")).classes("text-sm font-bold px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        for tot in slice_.month_actual_totals:
            ui.label(format_amount(tot or None)).classes(f"{cell_cls}").style(S_MON)
        ui.label(format_amount(slice_.grand_actual or None)).classes(
            "text-sm font-bold text-right px-3 py-2"
        ).style(S_TOT)
        ui.label("").style(S_ACT)


def _render_compare_grid(
    grid: AnnualPlanGrid,
    *,
    sub_bg: str,
    row_hover: str,
    hdr_cls: str,
    cell_cls: str,
    row_cls: str,
    is_dark: bool,
) -> None:
    act_bg = "bg-grey-8" if is_dark else "bg-grey-1"
    first_slice = grid.slices[0]

    for row in first_slice.rows:
        cat_label = row.name
        if row.is_child:
            cat_label = "   └ " + row.name
        with ui.row().classes(f"{row_cls} {sub_bg}"):
            ui.label(cat_label).classes("text-sm font-semibold px-3 py-1 flex-1")

        for slice_ in grid.slices:
            year_row = next(r for r in slice_.rows if r.category_id == row.category_id)
            rec_text, rec_color = recurring_display(year_row)

            with ui.row().classes(f"{row_cls} {row_hover}"):
                ui.label(str(slice_.year)).classes("text-xs text-grey-6 px-3 py-1 font-mono").style(
                    S_CAT
                )
                ui.label(rec_text).classes(f"{cell_cls} font-medium {rec_color}").style(S_REC)
                for cell in year_row.months:
                    color = "text-primary" if cell.planned else "text-grey-4"
                    ui.label(format_amount(cell.planned)).classes(f"{cell_cls} {color}").style(
                        S_MON
                    )
                ui.label(format_amount(year_row.total_planned or None)).classes(
                    "text-sm text-right px-3 py-1 font-medium"
                ).style(S_TOT)

            with ui.row().classes(f"items-center no-wrap gap-0 {act_bg}"):
                ui.label(f"{slice_.year} {t('budget_plan.actual')}").classes(
                    "text-xs text-grey-5 italic px-3 py-0"
                ).style(S_CAT)
                ui.label("").style(S_REC)
                for cell in year_row.months:
                    act_color = actual_cell_color(cell.actual, cell.is_over_budget)
                    ui.label(format_amount(cell.actual)).classes(
                        f"text-xs text-center py-0 px-1 {act_color}"
                    ).style(S_MON)
                ui.label(format_amount(year_row.total_actual or None)).classes(
                    "text-xs text-right px-3 py-0 text-grey-6"
                ).style(S_TOT)

    with ui.row().classes(f"{row_cls} {hdr_cls} font-bold border-t-2"):
        ui.label(t("common.total")).classes("text-sm font-bold px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        if grid.compare_month_totals is not None:
            for tot in grid.compare_month_totals:
                ui.label(format_amount(tot or None)).classes(f"{cell_cls} font-bold").style(S_MON)
        overall = grid.compare_grand_total or Decimal("0")
        ui.label(format_amount(overall or None)).classes(
            "text-sm font-bold text-right px-3 py-2"
        ).style(S_TOT)
