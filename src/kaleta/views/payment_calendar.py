"""Payment Calendar — month-grid view of planned transactions.

Each cell shows the day's inflow/outflow totals. Clicking a cell opens a
side-sheet with the day's occurrences and a Quick Add form. Overdue items
(planned in the trailing 30 days that have not happened yet) are pinned
above the selected day's list.

The flat list remains available via the 'List view' link — it navigates
back to the existing /planned page.
"""

from __future__ import annotations

import calendar
import datetime
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import Category
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import TransactionType
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.services import AccountService, CategoryService, PlannedTransactionService
from kaleta.services.planned_transaction_service import (
    DayAggregate,
    MonthGrid,
    PlannedOccurrence,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    PAGE_TITLE,
    SECTION_CARD,
    TOOLBAR_CARD,
)

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _build_cat_opts(cats_list: list[Category]) -> dict[int, str]:
    cats_by_id = {c.id: c for c in cats_list}
    result: dict[int, str] = {}
    roots = sorted(
        [c for c in cats_list if c.parent_id is None or c.parent_id not in cats_by_id],
        key=lambda c: c.name,
    )
    for root in roots:
        result[root.id] = root.name
        children = sorted([c for c in cats_list if c.parent_id == root.id], key=lambda c: c.name)
        for child in children:
            result[child.id] = f"{root.name} \u2192 {child.name}"
    return result


def _add_months(d: datetime.date, months: int) -> datetime.date:
    total = d.month + months
    year = d.year + (total - 1) // 12
    month = (total - 1) % 12 + 1
    return datetime.date(year, month, 1)


def _month_label(year: int, month: int) -> str:
    return f"{t(f'payment_calendar.month_{month}')} {year}"


def register() -> None:
    @ui.page("/payment-calendar")
    async def payment_calendar_page() -> None:
        today = datetime.date.today()
        state: dict[str, Any] = {
            "year": today.year,
            "month": today.month,
            "selected": today,
        }

        async with AsyncSessionFactory() as session:
            accounts = await AccountService(session).list()
            cats_list = await CategoryService(session).list()
        account_opts: dict[int, str] = {a.id: a.name for a in accounts}
        cat_opts = _build_cat_opts(cats_list)

        # ── Quick-add dialog ─────────────────────────────────────────────────
        quick_dialog = ui.dialog()
        with quick_dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(t("payment_calendar.quick_add_title")).classes("text-lg font-bold")
            q_name = ui.input(t("planned.name")).classes("w-full")
            with ui.row().classes("w-full gap-3"):
                q_account = ui.select(
                    account_opts, label=t("common.account")
                ).classes("flex-1")
                q_type = ui.select(
                    {
                        TransactionType.EXPENSE: t("common.expense"),
                        TransactionType.INCOME: t("common.income"),
                        TransactionType.TRANSFER: t("common.transfer"),
                    },
                    label=t("common.type"),
                    value=TransactionType.EXPENSE,
                ).classes("flex-1")
            with ui.row().classes("w-full gap-3"):
                q_amount = ui.number(
                    t("common.amount"), min=0.01, step=0.01, precision=2
                ).classes("flex-1")
                q_category = ui.select(
                    cat_opts, label=t("common.category"), clearable=True
                ).classes("flex-1")
            q_freq = ui.select(
                {
                    RecurrenceFrequency.ONCE: t("planned.freq_once"),
                    RecurrenceFrequency.WEEKLY: t("planned.freq_weekly"),
                    RecurrenceFrequency.MONTHLY: t("planned.freq_monthly"),
                    RecurrenceFrequency.YEARLY: t("planned.freq_yearly"),
                },
                label=t("planned.frequency"),
                value=RecurrenceFrequency.ONCE,
            ).classes("w-full")
            q_date_label = ui.label("").classes("text-sm text-slate-500")

            async def _quick_submit() -> None:
                name = (q_name.value or "").strip()
                if not name:
                    ui.notify(t("planned.name_required"), type="negative")
                    return
                if not q_account.value:
                    ui.notify(t("planned.account_required"), type="negative")
                    return
                if not q_amount.value or float(q_amount.value) <= 0:
                    ui.notify(t("planned.amount_required"), type="negative")
                    return
                payload = PlannedTransactionCreate(
                    name=name,
                    amount=q_amount.value,
                    type=q_type.value,
                    account_id=q_account.value,
                    category_id=q_category.value or None,
                    frequency=q_freq.value,
                    interval=1,
                    start_date=state["selected"],
                    is_active=True,
                )
                async with AsyncSessionFactory() as session:
                    await PlannedTransactionService(session).create(payload)
                ui.notify(t("planned.created"), type="positive")
                quick_dialog.close()
                await _refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=quick_dialog.close).props("flat")
                ui.button(
                    t("common.save"), icon="check", on_click=_quick_submit
                ).props("color=primary")

        def _open_quick_add(date: datetime.date) -> None:
            state["selected"] = date
            q_name.set_value("")
            q_account.set_value(next(iter(account_opts), None))
            q_type.set_value(TransactionType.EXPENSE)
            q_amount.set_value(None)
            q_category.set_value(None)
            q_freq.set_value(RecurrenceFrequency.ONCE)
            q_date_label.set_text(t("payment_calendar.quick_add_for", date=date.isoformat()))
            quick_dialog.open()

        # ── Day drawer (right side-sheet) ────────────────────────────────────
        day_dialog = ui.dialog().props("position=right")
        with day_dialog, ui.card().classes("w-[420px] h-screen gap-3 p-5"):
            day_header = ui.label("").classes("text-lg font-bold")
            day_totals = ui.label("").classes("text-sm text-slate-500")
            ui.separator()
            day_content = ui.column().classes("w-full gap-2 flex-1 overflow-y-auto")
            with ui.row().classes("w-full justify-between items-center mt-2"):
                ui.button(t("common.close"), on_click=day_dialog.close).props("flat")
                day_add_btn = ui.button(
                    t("payment_calendar.add_for_day"),
                    icon="add",
                    on_click=lambda: _open_quick_add(state["selected"]),
                ).props("color=primary")

        def _render_occurrence_row(
            occ: PlannedOccurrence, *, muted: bool = False
        ) -> None:
            is_income = occ.type == TransactionType.INCOME
            amt_cls = AMOUNT_INCOME if is_income else AMOUNT_EXPENSE
            sign = "+" if is_income else "-"
            row_cls = (
                "w-full items-center justify-between p-2 rounded-lg border "
                + ("border-slate-200/60 opacity-70" if muted else "border-slate-200/60")
            )
            with ui.row().classes(row_cls):
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(occ.name).classes("text-sm font-medium")
                    sub_parts = [occ.account_name]
                    if occ.category_name:
                        sub_parts.append(occ.category_name)
                    ui.label(" · ".join(sub_parts)).classes("text-xs text-slate-500")
                ui.label(f"{sign}{_fmt(abs(occ.amount))}").classes(
                    f"{amt_cls} text-sm font-semibold"
                )

        def _open_day(
            date: datetime.date,
            cell: DayAggregate | None,
            overdue: list[PlannedOccurrence],
        ) -> None:
            state["selected"] = date
            day_header.set_text(t("payment_calendar.day_header", date=date.isoformat()))
            if cell:
                day_totals.set_text(
                    f"{t('payment_calendar.in')}: +{_fmt(cell.inflow)}   "
                    f"{t('payment_calendar.out')}: -{_fmt(cell.outflow)}   "
                    f"{t('payment_calendar.net')}: {_fmt(cell.net)}"
                )
            else:
                day_totals.set_text(t("payment_calendar.day_empty_totals"))

            day_content.clear()
            with day_content:
                if overdue:
                    ui.label(t("payment_calendar.overdue_title")).classes(
                        "text-xs font-semibold uppercase tracking-wide text-red-7"
                    )
                    for occ in overdue:
                        _render_occurrence_row(occ, muted=True)
                    ui.separator().classes("my-2")

                ui.label(t("payment_calendar.day_items")).classes(
                    "text-xs font-semibold uppercase tracking-wide text-slate-500"
                )
                if cell and cell.occurrences:
                    for occ in cell.occurrences:
                        _render_occurrence_row(occ)
                else:
                    ui.label(t("payment_calendar.day_empty")).classes(
                        "text-sm text-slate-500 italic"
                    )
            day_add_btn.set_text(
                t("payment_calendar.add_for_day_short", date=date.isoformat())
            )
            day_dialog.open()

        # ── Main layout ──────────────────────────────────────────────────────
        with page_layout(t("payment_calendar.title"), wide=True):
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                ui.label(t("payment_calendar.title")).classes(PAGE_TITLE)
                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        icon="chevron_left",
                        on_click=lambda: _shift_month(-1),
                    ).props("flat round dense")
                    month_label = ui.label(_month_label(state["year"], state["month"])).classes(
                        "text-base font-semibold min-w-40 text-center"
                    )
                    ui.button(
                        icon="chevron_right",
                        on_click=lambda: _shift_month(1),
                    ).props("flat round dense")
                    ui.button(
                        t("payment_calendar.today"),
                        icon="today",
                        on_click=lambda: _goto(today.year, today.month),
                    ).props("flat color=primary dense")
                    ui.button(
                        t("payment_calendar.list_view"),
                        icon="list",
                        on_click=lambda: ui.navigate.to("/planned"),
                    ).props("flat color=primary dense")

            # Summary KPIs
            with ui.row().classes("w-full gap-3 flex-wrap"):
                kpi_in = ui.label("").classes(
                    f"{TOOLBAR_CARD} flex-1 min-w-48 {AMOUNT_INCOME} text-lg font-semibold"
                )
                kpi_out = ui.label("").classes(
                    f"{TOOLBAR_CARD} flex-1 min-w-48 {AMOUNT_EXPENSE} text-lg font-semibold"
                )
                kpi_net = ui.label("").classes(
                    f"{TOOLBAR_CARD} flex-1 min-w-48 text-lg font-semibold"
                )
                kpi_overdue = ui.label("").classes(
                    f"{TOOLBAR_CARD} flex-1 min-w-48 text-lg font-semibold text-amber-7"
                )

            # Calendar grid container
            grid_container = ui.column().classes(f"{SECTION_CARD} gap-2")

            async def _refresh() -> None:
                y, m = state["year"], state["month"]
                month_label.set_text(_month_label(y, m))
                async with AsyncSessionFactory() as session:
                    grid = await PlannedTransactionService(session).grid_for_month(y, m)

                kpi_in.set_text(
                    f"{t('payment_calendar.month_in')}: +{_fmt(grid.total_inflow())}"
                )
                kpi_out.set_text(
                    f"{t('payment_calendar.month_out')}: -{_fmt(grid.total_outflow())}"
                )
                kpi_net.set_text(
                    f"{t('payment_calendar.month_net')}: {_fmt(grid.total_net())}"
                )
                kpi_overdue.set_text(
                    f"{t('payment_calendar.overdue_count')}: {len(grid.overdue)}"
                )

                _draw_grid(grid)

            def _draw_grid(grid: MonthGrid) -> None:
                grid_container.clear()
                y, m = grid.year, grid.month
                first = datetime.date(y, m, 1)
                last_day = calendar.monthrange(y, m)[1]
                # Python: Monday = 0 ... Sunday = 6
                leading = first.weekday()
                total_cells = leading + last_day
                trailing = (7 - total_cells % 7) % 7
                total_cells += trailing

                with grid_container:
                    # Weekday header
                    with ui.grid(columns=7).classes("w-full gap-1"):
                        for key in _WEEKDAY_KEYS:
                            ui.label(t(f"payment_calendar.wd_{key}")).classes(
                                "text-[11px] font-semibold uppercase tracking-wide "
                                "text-slate-500 text-center"
                            )

                    # Day cells
                    with ui.grid(columns=7).classes("w-full gap-1"):
                        for idx in range(total_cells):
                            day_num = idx - leading + 1
                            if day_num < 1 or day_num > last_day:
                                ui.element("div").classes(
                                    "min-h-20 rounded-lg bg-slate-50/40 "
                                    "border border-dashed border-slate-200/40"
                                )
                                continue
                            date = datetime.date(y, m, day_num)
                            cell = grid.days.get(date)
                            is_today = date == datetime.date.today()
                            _draw_day_cell(
                                date=date,
                                cell=cell,
                                overdue=grid.overdue if day_num == 1 else [],
                                is_today=is_today,
                            )

            def _draw_day_cell(
                *,
                date: datetime.date,
                cell: DayAggregate | None,
                overdue: list[PlannedOccurrence],
                is_today: bool,
            ) -> None:
                border_cls = (
                    "border-primary ring-1 ring-primary/40"
                    if is_today
                    else "border-slate-200/70"
                )
                col = ui.column().classes(
                    "min-h-20 p-2 rounded-lg border "
                    f"{border_cls} bg-white/70 cursor-pointer "
                    "hover:bg-slate-50 transition-colors gap-1"
                )
                col.on(
                    "click",
                    lambda _e=None, d=date, c=cell, ov=overdue: _open_day(d, c, ov),
                )
                with col:
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(str(date.day)).classes(
                            "text-sm font-semibold "
                            + ("text-primary" if is_today else "text-slate-700")
                        )
                        if cell and cell.occurrences:
                            ui.badge(str(len(cell.occurrences))).props(
                                "color=primary outline rounded"
                            ).classes("text-[10px]")
                    if cell:
                        if cell.inflow > 0:
                            ui.label(f"+{_fmt(cell.inflow)}").classes(
                                f"{AMOUNT_INCOME} text-[11px] font-semibold"
                            )
                        if cell.outflow > 0:
                            ui.label(f"-{_fmt(cell.outflow)}").classes(
                                f"{AMOUNT_EXPENSE} text-[11px] font-semibold"
                            )

            def _shift_month(delta: int) -> None:
                new_first = _add_months(datetime.date(state["year"], state["month"], 1), delta)
                state["year"] = new_first.year
                state["month"] = new_first.month
                ui.timer(0.01, _refresh, once=True)

            def _goto(year: int, month: int) -> None:
                state["year"] = year
                state["month"] = month
                ui.timer(0.01, _refresh, once=True)

            await _refresh()
