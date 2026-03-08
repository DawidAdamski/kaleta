from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.models.category import Category, CategoryType
from kaleta.schemas.budget import BudgetCreate
from kaleta.services import BudgetService, CategoryService
from kaleta.views.layout import page_layout

MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Flex-based column styles — month columns grow to fill available width
_S_CAT = "flex: 0 0 175px; min-width: 0; overflow: hidden"
_S_REC = "flex: 0 0 82px"
_S_MON = "flex: 1 1 55px; min-width: 52px"
_S_TOT = "flex: 0 0 90px"
_S_ACT = "flex: 0 0 76px"
# Min total width so overflow-x-auto kicks in on narrow screens
_INNER_MIN = "min-width: 1020px; width: 100%"


def _sorted_with_children(cats: list[Category]) -> list[Category]:
    """Return categories sorted so each parent is immediately followed by its children."""
    children_by_parent: dict[int, list[Category]] = {}
    for c in cats:
        if c.parent_id:
            children_by_parent.setdefault(c.parent_id, []).append(c)
    result: list[Category] = []
    for parent in sorted((c for c in cats if c.parent_id is None), key=lambda c: c.name):
        result.append(parent)
        for child in sorted(children_by_parent.get(parent.id, []), key=lambda c: c.name):
            result.append(child)
    return result


def _monthly_value(bmap: dict[tuple[int, int], Decimal], cat_id: int) -> Decimal | None:
    """Return the uniform monthly amount if all 12 months are identical, else None."""
    amounts = [bmap.get((cat_id, m)) for m in range(1, 13)]
    if all(a is not None for a in amounts) and len(set(amounts)) == 1:
        return amounts[0]
    return None


def register() -> None:
    @ui.page("/budget-plan")
    async def budget_plan_page() -> None:
        today = datetime.date.today()
        state: dict = {
            "years": {today.year},
            "edit_year": today.year,   # year used by edit dialogs (single-year mode)
            "cat_id": None,
            "month": None,
        }

        # ── Cell dialog (single month) ─────────────────────────────────────
        with ui.dialog() as cell_dialog, ui.card().classes("w-72"):
            cell_title = ui.label("").classes("text-base font-bold mb-3")
            cell_amount = ui.number("Amount (zł)", min=0, format="%.2f").classes("w-full")
            ui.label("Set to 0 or leave empty to remove.").classes("text-xs text-grey-5 mt-1")

            async def save_cell() -> None:
                amount = Decimal(str(cell_amount.value or 0))
                cat_id: int = state["cat_id"]  # type: ignore[assignment]
                month: int = state["month"]  # type: ignore[assignment]
                year: int = state["edit_year"]
                async with AsyncSessionFactory() as session:
                    svc = BudgetService(session)
                    if amount > 0:
                        await svc.upsert(
                            BudgetCreate(
                                category_id=cat_id, amount=amount, month=month, year=year
                            )
                        )
                    else:
                        existing = await svc.get_by_category_period(cat_id, month, year)
                        if existing:
                            await svc.delete(existing.id)
                plan_grid.refresh()
                cell_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=cell_dialog.close).props("flat")
                ui.button("Save", on_click=save_cell).props("color=primary")

        # ── Monthly dialog (fill all 12 months) ────────────────────────────
        with ui.dialog() as monthly_dialog, ui.card().classes("w-72"):
            monthly_title = ui.label("").classes("text-base font-bold mb-1")
            ui.label(
                "Sets this amount for all 12 months. Individual months can still be overridden."
            ).classes("text-xs text-grey-5 mb-3")
            monthly_amount = ui.number("Monthly amount (zł)", min=0, format="%.2f").classes(
                "w-full"
            )

            async def save_monthly() -> None:
                try:
                    amount = Decimal(str(monthly_amount.value or 0))
                except InvalidOperation:
                    ui.notify("Invalid amount.", type="negative")
                    return
                if amount <= 0:
                    ui.notify("Amount must be greater than 0.", type="warning")
                    return
                cat_id: int = state["cat_id"]  # type: ignore[assignment]
                year: int = state["edit_year"]
                async with AsyncSessionFactory() as session:
                    svc = BudgetService(session)
                    for m in range(1, 13):
                        await svc.upsert(
                            BudgetCreate(
                                category_id=cat_id, amount=amount, month=m, year=year
                            )
                        )
                ui.notify("Monthly budget set for all 12 months.", type="positive")
                plan_grid.refresh()
                monthly_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=monthly_dialog.close).props("flat")
                ui.button("Apply to all 12 months", on_click=save_monthly).props("color=primary")

        # ── Yearly dialog (spread total evenly) ────────────────────────────
        with ui.dialog() as yearly_dialog, ui.card().classes("w-72"):
            yearly_title = ui.label("").classes("text-base font-bold mb-3")
            yearly_amount = ui.number("Yearly total (zł)", min=0, format="%.2f").classes("w-full")
            yearly_preview = ui.label("").classes("text-xs text-grey-5 mt-1")

            def _update_preview(e: object) -> None:  # noqa: ARG001
                try:
                    t = float(yearly_amount.value or 0)
                    yearly_preview.set_text(f"≈ {t / 12:,.2f} zł / month")
                except (TypeError, ZeroDivisionError):
                    yearly_preview.set_text("")

            yearly_amount.on_value_change(_update_preview)

            async def save_yearly() -> None:
                try:
                    total = Decimal(str(yearly_amount.value or 0))
                except InvalidOperation:
                    ui.notify("Invalid amount.", type="negative")
                    return
                if total <= 0:
                    ui.notify("Amount must be greater than 0.", type="warning")
                    return
                monthly = (total / 12).quantize(Decimal("0.01"))
                cat_id: int = state["cat_id"]  # type: ignore[assignment]
                year: int = state["edit_year"]
                async with AsyncSessionFactory() as session:
                    svc = BudgetService(session)
                    for m in range(1, 13):
                        await svc.upsert(
                            BudgetCreate(
                                category_id=cat_id, amount=monthly, month=m, year=year
                            )
                        )
                ui.notify(f"Yearly budget set ({monthly:,.2f} zł/month).", type="positive")
                plan_grid.refresh()
                yearly_dialog.close()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=yearly_dialog.close).props("flat")
                ui.button("Distribute evenly", on_click=save_yearly).props("color=primary")

        # ── Grid ───────────────────────────────────────────────────────────
        @ui.refreshable
        async def plan_grid() -> None:
            is_dark: bool = app.storage.user.get("dark_mode", False)
            selected_years = sorted(state["years"])
            is_compare = len(selected_years) > 1

            async with AsyncSessionFactory() as session:
                all_cats = await CategoryService(session).list(type=CategoryType.EXPENSE)
                bmaps: dict[int, dict[tuple[int, int], Decimal]] = {}
                for y in selected_years:
                    budgets = await BudgetService(session).list_for_year(y)
                    bmaps[y] = {(b.category_id, b.month): b.amount for b in budgets}

            sorted_cats = _sorted_with_children(all_cats)

            hdr_cls = "bg-grey-9 text-grey-1" if is_dark else "bg-grey-2 text-grey-9"
            row_hover = "hover:bg-grey-9" if is_dark else "hover:bg-grey-1"
            sub_bg = "bg-grey-8" if is_dark else "bg-grey-1"
            cell_cls = "text-sm text-center py-1 px-1"
            row_cls = "items-center no-wrap gap-0 border-b"

            def _open_cell(
                cat_id: int, month: int, cat_name: str, current: Decimal | None
            ) -> None:
                state["cat_id"] = cat_id
                state["month"] = month
                cell_title.set_text(
                    f"{cat_name} — {MONTH_LABELS[month - 1]} {state['edit_year']}"
                )
                cell_amount.set_value(float(current) if current else 0)
                cell_dialog.open()

            def _open_monthly(cat_id: int, cat_name: str, suggest: float = 0.0) -> None:
                state["cat_id"] = cat_id
                monthly_title.set_text(cat_name)
                monthly_amount.set_value(round(suggest, 2))
                monthly_dialog.open()

            def _open_yearly(cat_id: int, cat_name: str, bmap: dict) -> None:
                state["cat_id"] = cat_id
                yearly_title.set_text(cat_name)
                total = sum(bmap.get((cat_id, m), Decimal("0")) for m in range(1, 13))
                yearly_amount.set_value(float(total))
                yearly_preview.set_text(
                    f"≈ {float(total) / 12:,.2f} zł / month" if total else ""
                )
                yearly_dialog.open()

            async def _clear_category(cat_id: int) -> None:
                async with AsyncSessionFactory() as session:
                    await BudgetService(session).delete_all_for_category_year(
                        cat_id, state["edit_year"]
                    )
                plan_grid.refresh()

            def _render_month_cells(
                bmap: dict[tuple[int, int], Decimal],
                cat_id: int,
                rec_value: Decimal | None,
                month_totals: list[Decimal],
                clickable: bool = True,
            ) -> Decimal:
                """Render 12 month cells for a row; return category total."""
                cat_total = Decimal("0")
                for idx, m in enumerate(range(1, 13)):
                    amount = bmap.get((cat_id, m))
                    if amount:
                        cat_total += amount
                        month_totals[idx] += amount
                    is_override = (
                        amount is not None and rec_value is not None and amount != rec_value
                    )
                    label_text = f"{amount:,.0f}" if amount else "—"
                    color = (
                        "text-orange-8" if is_override
                        else "text-primary" if amount
                        else "text-grey-4"
                    )
                    lbl = (
                        ui.label(label_text)
                        .classes(f"{cell_cls} {color}")
                        .style(_S_MON)
                    )
                    if clickable:
                        lbl.classes("cursor-pointer hover:bg-blue-1 rounded")
                        lbl.on(
                            "click",
                            lambda c_id=cat_id, mo=m, a=amount: _open_cell(c_id, mo, "", a),
                        )
                return cat_total

            # ── Table ─────────────────────────────────────────────────────
            with ui.element("div").classes(
                "overflow-x-auto w-full rounded-lg border"
            ), ui.element("div").style(_INNER_MIN):

                # Header
                with ui.row().classes(f"{row_cls} {hdr_cls} font-bold"):
                    ui.label("Category").classes("text-sm font-bold px-3 py-2").style(_S_CAT)
                    if not is_compare:
                        ui.label("Monthly").classes(
                            f"{cell_cls} font-bold"
                        ).style(_S_REC)
                    else:
                        ui.label("Year").classes(
                            f"{cell_cls} font-bold"
                        ).style(_S_REC)
                    for m_lbl in MONTH_LABELS:
                        ui.label(m_lbl).classes(f"{cell_cls} font-bold").style(_S_MON)
                    ui.label("Year total").classes(
                        "text-sm font-bold px-3 py-2 text-right"
                    ).style(_S_TOT)
                    if not is_compare:
                        ui.label("Actions").classes("text-sm font-bold px-3 py-2").style(_S_ACT)

                # ── Single-year planning mode ──────────────────────────────
                if not is_compare:
                    bmap = bmaps[selected_years[0]]
                    month_totals = [Decimal("0")] * 12

                    for cat in sorted_cats:
                        is_child = cat.parent_id is not None
                        rec_value = _monthly_value(bmap, cat.id)
                        any_set = any(bmap.get((cat.id, m)) for m in range(1, 13))

                        if rec_value is not None:
                            rec_text = f"{rec_value:,.0f}"
                            rec_color = "text-primary cursor-pointer"
                        elif any_set:
                            rec_text = "~"
                            rec_color = "text-orange-8 cursor-pointer"
                        else:
                            rec_text = "—"
                            rec_color = "text-grey-4 cursor-pointer"

                        name_suffix = " text-grey-6 pl-7" if is_child else " font-medium"
                        name_cls = "text-sm px-3 py-2 truncate" + name_suffix

                        with ui.row().classes(f"{row_cls} {row_hover}"):
                            with ui.element("div").style(_S_CAT).classes(
                                "flex items-center gap-1 py-1 overflow-hidden"
                            ):
                                if is_child:
                                    ui.icon("subdirectory_arrow_right").classes(
                                        "text-grey-5 ml-2 text-sm flex-shrink-0"
                                    )
                                ui.label(cat.name).classes(name_cls).style(
                                    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                                )

                            # Monthly recurring cell
                            suggest = float(rec_value) if rec_value else 0.0
                            (
                                ui.label(rec_text)
                                .classes(f"{cell_cls} font-medium {rec_color}")
                                .style(_S_REC)
                                .on(
                                    "click",
                                    lambda c=cat, s=suggest: _open_monthly(c.id, c.name, s),
                                )
                            )

                            # Month cells (with cell-open on click)
                            cat_total = Decimal("0")
                            for idx, m in enumerate(range(1, 13)):
                                amount = bmap.get((cat.id, m))
                                if amount:
                                    cat_total += amount
                                    month_totals[idx] += amount
                                is_override = (
                                    amount is not None
                                    and rec_value is not None
                                    and amount != rec_value
                                )
                                label_text = f"{amount:,.0f}" if amount else "—"
                                color = (
                                    "text-orange-8" if is_override
                                    else "text-primary" if amount
                                    else "text-grey-4"
                                )
                                (
                                    ui.label(label_text)
                                    .classes(
                                        f"{cell_cls} cursor-pointer hover:bg-blue-1 rounded {color}"
                                    )
                                    .style(_S_MON)
                                    .on(
                                        "click",
                                        lambda c=cat, mo=m, a=amount: _open_cell(
                                            c.id, mo, c.name, a
                                        ),
                                    )
                                )

                            ui.label(f"{cat_total:,.0f}" if cat_total else "—").classes(
                                "text-sm text-right px-3 py-2 font-medium"
                            ).style(_S_TOT)

                            with ui.row().classes("gap-0 px-1 items-center").style(_S_ACT):
                                ui.button(
                                    icon="event_note",
                                    on_click=lambda c=cat, bm=bmap: _open_yearly(
                                        c.id, c.name, bm
                                    ),
                                ).props("flat round dense size=sm color=orange-8").tooltip(
                                    "Set from yearly total"
                                )
                                ui.button(
                                    icon="delete_sweep",
                                    on_click=lambda c=cat: _clear_category(c.id),
                                ).props("flat round dense size=sm color=negative").tooltip(
                                    "Clear all months"
                                )

                    # Totals row
                    grand_total = sum(month_totals)
                    with ui.row().classes(f"{row_cls} {hdr_cls} font-bold border-t-2"):
                        ui.label("TOTAL").classes("text-sm font-bold px-3 py-2").style(_S_CAT)
                        ui.label("").style(_S_REC)
                        for t in month_totals:
                            ui.label(f"{t:,.0f}" if t else "—").classes(
                                f"{cell_cls} font-bold"
                            ).style(_S_MON)
                        ui.label(f"{grand_total:,.0f}" if grand_total else "—").classes(
                            "text-sm font-bold text-right px-3 py-2"
                        ).style(_S_TOT)
                        ui.label("").style(_S_ACT)

                # ── Multi-year comparison mode ─────────────────────────────
                else:
                    grand_totals: dict[int, Decimal] = {y: Decimal("0") for y in selected_years}

                    for cat in sorted_cats:
                        is_child = cat.parent_id is not None
                        # Category label row (spans all content, no data)
                        cat_label = cat.name
                        if is_child:
                            cat_label = "   └ " + cat.name
                        with ui.row().classes(f"{row_cls} {sub_bg}"):
                            ui.label(cat_label).classes(
                                "text-sm font-semibold px-3 py-1 flex-1"
                            )

                        # One sub-row per year
                        for y in selected_years:
                            bmap = bmaps[y]
                            rec_value = _monthly_value(bmap, cat.id)
                            any_set = any(bmap.get((cat.id, m)) for m in range(1, 13))

                            if rec_value is not None:
                                rec_text = f"{rec_value:,.0f}"
                                rec_color = "text-primary"
                            elif any_set:
                                rec_text = "~"
                                rec_color = "text-orange-8"
                            else:
                                rec_text = "—"
                                rec_color = "text-grey-4"

                            cat_total = Decimal("0")
                            with ui.row().classes(f"{row_cls} {row_hover}"):
                                # Year label in category column (indented)
                                ui.label(str(y)).classes(
                                    "text-xs text-grey-6 px-3 py-1 font-mono"
                                ).style(_S_CAT)

                                # Monthly column
                                ui.label(rec_text).classes(
                                    f"{cell_cls} font-medium {rec_color}"
                                ).style(_S_REC)

                                # Month cells (read-only)
                                for m in range(1, 13):
                                    amount = bmap.get((cat.id, m))
                                    if amount:
                                        cat_total += amount
                                    label_text = f"{amount:,.0f}" if amount else "—"
                                    color = "text-primary" if amount else "text-grey-4"
                                    ui.label(label_text).classes(
                                        f"{cell_cls} {color}"
                                    ).style(_S_MON)

                                ui.label(f"{cat_total:,.0f}" if cat_total else "—").classes(
                                    "text-sm text-right px-3 py-1 font-medium"
                                ).style(_S_TOT)
                                grand_totals[y] += cat_total

                    # Totals row per year
                    with ui.row().classes(f"{row_cls} {hdr_cls} font-bold border-t-2"):
                        ui.label("TOTAL").classes("text-sm font-bold px-3 py-2").style(_S_CAT)
                        ui.label("").style(_S_REC)
                        # Show grand totals summed across all years (per month column)
                        month_col_totals = [Decimal("0")] * 12
                        for y in selected_years:
                            bmap = bmaps[y]
                            for idx, m in enumerate(range(1, 13)):
                                for c in sorted_cats:
                                    v = bmap.get((c.id, m))
                                    if v:
                                        month_col_totals[idx] += v
                        for t in month_col_totals:
                            ui.label(f"{t:,.0f}" if t else "—").classes(
                                f"{cell_cls} font-bold"
                            ).style(_S_MON)
                        overall = sum(grand_totals.values())
                        ui.label(f"{overall:,.0f}" if overall else "—").classes(
                            "text-sm font-bold text-right px-3 py-2"
                        ).style(_S_TOT)

        # ── Page layout ─────────────────────────────────────────────────────
        available_years = list(range(today.year - 4, today.year + 2))

        def _toggle_year(y: int) -> None:
            if y in state["years"] and len(state["years"]) > 1:
                state["years"].discard(y)
            elif y not in state["years"]:
                state["years"].add(y)
            else:
                return  # last remaining year — don't deselect
            if len(state["years"]) == 1:
                state["edit_year"] = next(iter(state["years"]))
            year_chips.refresh()
            plan_grid.refresh()

        with page_layout("Budget Plan"):
            with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                ui.label("Budget Plan").classes("text-2xl font-bold")
                ui.space()
                ui.label("Years:").classes("text-sm text-grey-6")

                @ui.refreshable
                def year_chips() -> None:
                    for y in available_years:
                        active = y in state["years"]
                        ui.button(
                            str(y),
                            on_click=lambda yr=y: _toggle_year(yr),
                        ).props(
                            f"rounded dense {'color=primary' if active else 'outline color=grey-6'}"
                        )

                year_chips()

            ui.label(
                "Single year: click Monthly column to set all 12 months; click a cell to override. "
                "Multiple years: read-only comparison. Orange ~ = mixed amounts."
            ).classes("text-sm text-grey-6")

            await plan_grid()
