# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan annual grid — single-year and multi-year compare rendering."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import BudgetService, with_session
from kaleta.services.budget_service import AnnualPlanGrid, PlanCategoryRow, YearPlanSlice
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
from kaleta.views.theme import (
    INK,
    MONO,
    MUTED,
    PLAN_ACTUAL_ROW,
    PLAN_CELL_EDIT,
    PLAN_GRID,
    PLAN_HEAD,
    PLAN_MONTH_NOW,
    PLAN_ROW,
    PLAN_RULE,
    PLAN_TOTAL,
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
        selected_years = sorted(state["years"])

        async def _load(session: Any) -> AnnualPlanGrid:
            return await BudgetService(session).load_annual_plan_grid(selected_years)

        grid = await with_session(_load)

        # No card, no shadow, no slate: artboard 2c gives the densest screen
        # in the app the opposite treatment — hairlines, and the paper is the
        # table. ``is_dark`` no longer decides anything here; the tokens do.
        cell_cls = "text-sm text-center py-1 px-1"
        row_cls = "items-center no-wrap gap-0"

        async def _clear_category(cat_id: int) -> None:
            async def _run(session: Any) -> None:
                await BudgetService(session).delete_all_for_category_year(
                    cat_id, state["edit_year"]
                )

            await with_session(_run)
            on_refresh()

        # This grid does not reflow — twelve month columns cannot become one.
        # It scrolls sideways instead, which the handoff calls for by name.
        with (
            ui.element("div").classes(f"overflow-x-auto w-full {PLAN_GRID}"),
            ui.element("div").style(INNER_MIN),
        ):
            # One "today" for the whole render: a page drawn across midnight on
            # the 1st would otherwise tint December in the header and January
            # in the rows.
            now = datetime.date.today()
            _render_header(grid, row_cls=row_cls, cell_cls=cell_cls, now=now)

            if not grid.is_compare:
                slice_ = grid.slices[0]
                _render_single_year_grid(
                    slice_,
                    budget_map=slice_.budget_map,
                    dialogs=dialogs,
                    cell_cls=cell_cls,
                    row_cls=row_cls,
                    now=now,
                    clear_category=_clear_category,
                )
            else:
                _render_compare_grid(grid, cell_cls=cell_cls, row_cls=row_cls)

    return plan_grid


def _render_header(
    grid: AnnualPlanGrid,
    *,
    row_cls: str,
    cell_cls: str,
    now: datetime.date,
) -> None:
    year = grid.slices[0].year if not grid.is_compare else None
    with ui.row().classes(f"{row_cls} {PLAN_HEAD} k-eyebrow"):
        ui.label(t("common.category")).classes("px-3 py-2").style(S_CAT)
        ui.label(t("common.month") if not grid.is_compare else t("common.year")).classes(
            cell_cls
        ).style(S_REC)
        for index, month_lbl in enumerate(month_labels(), start=1):
            tint = PLAN_MONTH_NOW if (year == now.year and index == now.month) else ""
            ui.label(month_lbl).classes(f"{cell_cls} {tint}").style(S_MON)
        ui.label(t("budget_plan.year_total")).classes(
            "px-3 py-2 text-right whitespace-nowrap"
        ).style(S_TOT)
        if not grid.is_compare:
            # The two row actions moved into a right-click menu to buy back
            # the width twelve month columns need; the header says so, and the
            # per-row button keeps them reachable without a mouse button.
            with ui.element("div").classes("flex items-center justify-center").style(S_ACT):
                hint = ui.icon("more_horiz", size="16px")
                hint.tooltip(t("budget_plan.row_actions_hint"))
                # A bare <i> with a label and no role announces nothing.
                hint.props('role="img"')
                hint.props["aria-label"] = t("budget_plan.row_actions_hint")


def _row_actions(
    row: PlanCategoryRow,
    *,
    budget_map: dict[tuple[int, int], Decimal],
    dialogs: EditDialogs,
    clear_category: Callable[[int], Awaitable[None]],
) -> None:
    """The two row actions, as menu items rather than two always-on buttons."""
    ui.menu_item(
        t("budget_plan.set_from_yearly"),
        on_click=lambda: dialogs.open_yearly(
            cat_id=row.category_id, cat_name=row.name, budget_map=budget_map
        ),
    )
    ui.menu_item(
        t("budget_plan.clear_all"),
        on_click=lambda: clear_category(row.category_id),
    )


def _render_single_year_grid(
    slice_: YearPlanSlice,
    *,
    budget_map: dict[tuple[int, int], Decimal],
    dialogs: EditDialogs,
    cell_cls: str,
    row_cls: str,
    now: datetime.date,
    clear_category: Callable[[int], Awaitable[None]],
) -> None:
    this_month = now.month if slice_.year == now.year else None

    for row in slice_.rows:
        rec_text, rec_color = recurring_display(row)
        name_suffix = f" {MUTED} pl-7" if row.is_child else f" {INK} font-medium"
        name_cls = "text-sm px-3 py-2 truncate" + name_suffix

        # The plan line and its actual line are one category: they share a
        # hairline and light up together, rather than reading as two rows
        # that happen to sit next to each other.
        with ui.column().classes(f"w-full gap-0 {PLAN_ROW}"):
            # Right-click anywhere on the pair, which is where the actions went.
            with ui.context_menu():
                _row_actions(
                    row,
                    budget_map=budget_map,
                    dialogs=dialogs,
                    clear_category=clear_category,
                )
            with ui.row().classes(f"{row_cls} w-full"):
                with (
                    ui.element("div")
                    .style(S_CAT)
                    .classes("flex items-center gap-1 py-1 overflow-hidden")
                ):
                    if row.is_child:
                        ui.icon("subdirectory_arrow_right").classes(
                            f"{MUTED} ml-2 text-sm flex-shrink-0"
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
                        lambda r=row, sug=suggest: dialogs.open_monthly(
                            cat_id=r.category_id, cat_name=r.name, suggest=sug
                        ),
                    )
                )

                for cell in row.months:
                    color = plan_cell_color(cell.planned, cell.is_override)
                    tint = PLAN_MONTH_NOW if cell.month == this_month else ""
                    (
                        ui.label(format_amount(cell.planned))
                        .classes(
                            f"{cell_cls} {MONO} {PLAN_CELL_EDIT} cursor-pointer {color} {tint}"
                        )
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
                    f"text-sm text-right px-3 py-2 font-medium {MONO} {INK}"
                ).style(S_TOT)

                with ui.element("div").classes("flex items-center justify-center").style(S_ACT):
                    # The same menu the right-click opens, for touch and for
                    # anyone who has never right-clicked a table row.
                    actions_button = ui.button(icon="more_horiz").props(
                        "flat round dense size=sm color=grey-7"
                    )
                    actions_button.tooltip(t("budget_plan.row_actions"))
                    actions_button.props["aria-label"] = (
                        f"{t('budget_plan.row_actions')}: {row.name}"
                    )
                    with actions_button, ui.menu():
                        _row_actions(
                            row,
                            budget_map=budget_map,
                            dialogs=dialogs,
                            clear_category=clear_category,
                        )

            if not row.show_actual_row:
                continue
            with ui.row().classes(f"{row_cls} w-full {PLAN_ACTUAL_ROW}"):
                ui.label(t("budget_plan.actual_row")).classes(
                    f"text-[10.5px] {MUTED} px-3 py-0"
                ).style(S_CAT)
                ui.label("").style(S_REC)
                for cell in row.months:
                    act_color = actual_cell_color(cell.actual, cell.is_over_budget)
                    tint = PLAN_MONTH_NOW if cell.month == this_month else ""
                    ui.label(format_amount(cell.actual)).classes(
                        f"text-[10.5px] {MONO} text-center py-0 px-1 {act_color} {tint}"
                    ).style(S_MON)
                ui.label(format_amount(row.total_actual or None)).classes(
                    f"text-[10.5px] {MONO} {MUTED} text-right px-3 py-0"
                ).style(S_TOT)
                ui.label("").style(S_ACT)

    with ui.row().classes(f"{row_cls} {PLAN_TOTAL} {INK} font-medium"):
        ui.label(t("budget_plan.planned")).classes("text-sm px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        for index, tot in enumerate(slice_.month_planned_totals, start=1):
            tint = PLAN_MONTH_NOW if index == this_month else ""
            ui.label(format_amount(tot or None)).classes(f"{cell_cls} {MONO} {tint}").style(S_MON)
        ui.label(format_amount(slice_.grand_planned or None)).classes(
            f"text-sm text-right px-3 py-2 {MONO}"
        ).style(S_TOT)
        ui.label("").style(S_ACT)

    with ui.row().classes(f"{row_cls} {MUTED}"):
        ui.label(t("budget_plan.actual")).classes("text-sm px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        for index, tot in enumerate(slice_.month_actual_totals, start=1):
            tint = PLAN_MONTH_NOW if index == this_month else ""
            ui.label(format_amount(tot or None)).classes(f"{cell_cls} {MONO} {tint}").style(S_MON)
        ui.label(format_amount(slice_.grand_actual or None)).classes(
            f"text-sm text-right px-3 py-2 {MONO}"
        ).style(S_TOT)
        ui.label("").style(S_ACT)


def _render_compare_grid(
    grid: AnnualPlanGrid,
    *,
    cell_cls: str,
    row_cls: str,
) -> None:
    first_slice = grid.slices[0]

    for row in first_slice.rows:
        cat_label = row.name
        if row.is_child:
            cat_label = "   └ " + row.name
        # A hairline, and the name as the user typed it: `k-eyebrow` would
        # uppercase "Żywność" and strong rules belong to the header and the
        # totals band alone.
        with ui.row().classes(f"{row_cls} {PLAN_RULE} mt-3"):
            ui.label(cat_label).classes(f"text-sm font-medium {INK} px-3 py-1 flex-1")

        for slice_ in grid.slices:
            year_row = next(r for r in slice_.rows if r.category_id == row.category_id)
            rec_text, rec_color = recurring_display(year_row)

            with ui.column().classes(f"w-full gap-0 {PLAN_ROW}"):
                with ui.row().classes(f"{row_cls} w-full"):
                    ui.label(str(slice_.year)).classes(f"text-xs {MUTED} px-3 py-1 {MONO}").style(
                        S_CAT
                    )
                    ui.label(rec_text).classes(f"{cell_cls} font-medium {rec_color}").style(S_REC)
                    for cell in year_row.months:
                        color = INK if cell.planned else MUTED
                        ui.label(format_amount(cell.planned)).classes(
                            f"{cell_cls} {MONO} {color}"
                        ).style(S_MON)
                    ui.label(format_amount(year_row.total_planned or None)).classes(
                        f"text-sm text-right px-3 py-1 font-medium {MONO} {INK}"
                    ).style(S_TOT)

                # The actual line stays, inside the pair. Scope's "no sub-rows"
                # reads two ways, and the reading that deletes a year's
                # spending from the only screen showing it beside another
                # year's is the wrong one to pick on your own.
                with ui.row().classes(f"{row_cls} w-full {PLAN_ACTUAL_ROW}"):
                    ui.label(t("budget_plan.actual_row")).classes(
                        f"text-[10.5px] {MUTED} px-3 py-0"
                    ).style(S_CAT)
                    ui.label("").style(S_REC)
                    for cell in year_row.months:
                        act_color = actual_cell_color(cell.actual, cell.is_over_budget)
                        ui.label(format_amount(cell.actual)).classes(
                            f"text-[10.5px] {MONO} text-center py-0 px-1 {act_color}"
                        ).style(S_MON)
                    ui.label(format_amount(year_row.total_actual or None)).classes(
                        f"text-[10.5px] {MONO} {MUTED} text-right px-3 py-0"
                    ).style(S_TOT)

    with ui.row().classes(f"{row_cls} {PLAN_TOTAL} {INK} font-medium"):
        ui.label(t("common.total")).classes("text-sm px-3 py-2").style(S_CAT)
        ui.label("").style(S_REC)
        if grid.compare_month_totals is not None:
            for tot in grid.compare_month_totals:
                ui.label(format_amount(tot or None)).classes(f"{cell_cls} {MONO}").style(S_MON)
        overall = grid.compare_grand_total or Decimal("0")
        ui.label(format_amount(overall or None)).classes(
            f"text-sm text-right px-3 py-2 {MONO}"
        ).style(S_TOT)
