# SPDX-License-Identifier: AGPL-3.0-or-later
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
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import plural_key, t
from kaleta.schemas.planned_transaction import PlannedTransactionCreate, RecurrenceFrequency
from kaleta.schemas.transaction import TransactionType
from kaleta.schemas.wizard_projections import SubscriptionCharge
from kaleta.services import (
    AccountService,
    CategoryService,
    PlannedTransactionService,
    WizardProjectionService,
    with_session,
)
from kaleta.services.planned_transaction_service import (
    DayAggregate,
    MonthGrid,
    PlannedOccurrence,
)
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.settings.constants import DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    AMOUNT_NEUTRAL,
    BODY_MUTED,
    CALENDAR_DAY,
    CALENDAR_DAY_BLANK,
    CALENDAR_DAY_NUM,
    CALENDAR_DAY_SELECTED,
    CALENDAR_DAY_TODAY,
    CALENDAR_DOT,
    CALENDAR_DOT_FLAT,
    CALENDAR_DOT_IN,
    CALENDAR_DOT_OUT,
    HAIRLINE_ROW,
    INK,
    KPI_VALUE,
    MONO,
    MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_TITLE,
    TOOLBAR_CARD,
    WARNING_STRIP,
)

_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

#: How many dots fit in a cell before the rest become a "+N" tail. Eight is
#: what a cell holds at the narrowest column width without wrapping to a
#: second row and pushing the grid taller.
DOT_CAP = 8


@dataclass(frozen=True, slots=True)
class DayMarks:
    """What one day cell draws: a net figure, and one dot per thing happening.

    The cell used to stack an inflow line, an outflow line and a count badge —
    three numbers, thirty-one times over, none of which could be compared
    across a row at a glance. The net says which way the day goes; the dots
    say how busy it is, which is what the counts were really for.
    """

    net: Decimal
    dots: tuple[str, ...]
    overflow: int

    @property
    def is_empty(self) -> bool:
        return not self.dots


def day_marks(
    cell: DayAggregate | None,
    subscriptions: Sequence[SubscriptionCharge],
    *,
    cap: int = DOT_CAP,
) -> DayMarks:
    """Reduce a day's occurrences and subscription charges to net plus dots.

    A transfer is drawn flat, not as an outflow: the service counts it in
    neither inflow nor outflow, so colouring it would give the day a
    direction its own net does not have. Projected subscription charges are
    flat too — they are the only items in the cell you cannot post.
    """
    dots: list[str] = []
    for occ in cell.occurrences if cell else ():
        if occ.type == TransactionType.INCOME:
            dots.append(CALENDAR_DOT_IN)
        elif occ.type == TransactionType.EXPENSE:
            dots.append(CALENDAR_DOT_OUT)
        else:
            dots.append(CALENDAR_DOT_FLAT)
    dots.extend(CALENDAR_DOT_FLAT for _ in subscriptions)

    subs_total = sum((s.amount for s in subscriptions), Decimal("0"))
    net = (cell.net if cell else Decimal("0")) - subs_total
    return DayMarks(net=net, dots=tuple(dots[:cap]), overflow=max(0, len(dots) - cap))


def actually_overdue(
    occurrences: Sequence[PlannedOccurrence], today: datetime.date
) -> list[PlannedOccurrence]:
    """The ones that are genuinely late, in date order.

    ``grid_for_month`` windows its overdue bucket against the *browsed*
    month, not against today: it returns the unposted occurrences in the
    thirty days before the first of whichever month is on screen. Page
    forward one month and that window lands in the future, where nothing can
    be late — and an age computed from it would read "-5 days late". The
    strip and the overdue count both take this filter, so they agree.
    """
    return sorted((o for o in occurrences if o.date < today), key=lambda o: o.date)


def overdue_age_label(occ_date: datetime.date, today: datetime.date) -> str:
    """ "3 days" — how long the item has been waiting, in Polish-aware plurals."""
    days = (today - occ_date).days
    return t(plural_key("payment_calendar.overdue_age", days), days=days)


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


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
            # dict[date, list[SubscriptionCharge]] — populated on refresh.
            "subs_by_day": {},
            # The month in hand, and the cell element for each of its days.
            "grid": None,
            "cells": {},
        }

        async def _load_refs(session: Any) -> tuple[dict[int, str], dict[int, str]]:
            accounts = await AccountService(session).list()
            cats_list = await CategoryService(session).list()
            return (
                {a.id: a.name for a in accounts},
                CategoryService.build_option_labels(cats_list),
            )

        account_opts, cat_opts = await with_session(_load_refs)

        # ── Quick-add dialog ─────────────────────────────────────────────────
        quick_dialog = ui.dialog()
        with quick_dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(t("payment_calendar.quick_add_title")).classes("text-lg font-bold")
            q_name = ui.input(t("planned.name")).classes("w-full")
            with ui.row().classes("w-full gap-3"):
                q_account = ui.select(account_opts, label=t("common.account")).classes("flex-1")
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
                q_amount = ui.number(t("common.amount"), min=0.01, step=0.01, precision=2).classes(
                    "flex-1"
                )
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
            q_date_label = ui.label("").classes(BODY_MUTED)

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

                async def _create(session: Any) -> None:
                    await PlannedTransactionService(session).create(payload)

                await with_session(_create)
                ui.notify(t("planned.created"), type="positive")
                quick_dialog.close()
                await _refresh()

            with ui.row().classes("w-full justify-end gap-2 mt-1"):
                ui.button(t("common.cancel"), on_click=quick_dialog.close).props("flat")
                ui.button(t("common.save"), icon="check", on_click=_quick_submit).props(
                    "color=primary"
                )

        def _open_quick_add(date: datetime.date) -> None:
            _select_day(date)
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
            day_totals = ui.label("").classes(f"{BODY_MUTED} {MONO}")
            ui.separator()
            day_content = ui.column().classes("w-full gap-2 flex-1 overflow-y-auto")
            with ui.row().classes("w-full justify-between items-center mt-2"):
                ui.button(t("common.close"), on_click=day_dialog.close).props("flat")
                day_add_btn = ui.button(
                    t("payment_calendar.add_for_day"),
                    icon="add",
                    on_click=lambda: _open_quick_add(state["selected"]),
                ).props("color=primary")

        def _lookback_days() -> int:
            return (
                int(app.storage.user.get("payment_calendar_overdue_days", 0) or 0)
                or DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS
            )

        async def _post_occurrence(occ: PlannedOccurrence) -> None:
            try:

                async def _run(session: Any) -> None:
                    await PlannedTransactionService(session).post_occurrence(
                        occ.planned_id, occ.date
                    )

                await with_session(_run)
            except KaletaError as exc:
                notify_kaleta_error(exc)
                return
            ui.notify(t("payment_calendar.posted", name=occ.name), type="positive")
            day_dialog.close()
            await _refresh()

        async def _post_all_due() -> None:
            try:

                async def _run(session: Any) -> int:
                    posted = await PlannedTransactionService(session).post_due(
                        lookback_days=_lookback_days()
                    )
                    return len(posted)

                count = await with_session(_run)
            except KaletaError as exc:
                notify_kaleta_error(exc)
                return
            if count:
                ui.notify(t("payment_calendar.posted_all", count=count), type="positive")
            else:
                ui.notify(t("payment_calendar.posted_none"), type="info")
            await _refresh()

        def _render_occurrence_row(occ: PlannedOccurrence, *, muted: bool = False) -> None:
            is_income = occ.type == TransactionType.INCOME
            amt_cls = AMOUNT_INCOME if is_income else AMOUNT_EXPENSE
            sign = "+" if is_income else "-"
            row_cls = f"{HAIRLINE_ROW} w-full items-center justify-between p-2 rounded-lg" + (
                " opacity-70" if muted else ""
            )
            can_post = occ.date <= datetime.date.today()
            with ui.row().classes(row_cls):
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(occ.name).classes("text-sm font-medium")
                    sub_parts = [occ.account_name]
                    if occ.category_name:
                        sub_parts.append(occ.category_name)
                    ui.label(" · ".join(sub_parts)).classes(f"{MUTED} text-xs")
                with ui.row().classes("items-center gap-2"):
                    ui.label(f"{sign}{_fmt(abs(occ.amount))}").classes(
                        f"{amt_cls} text-sm font-semibold"
                    )
                    if can_post:
                        ui.button(
                            t("payment_calendar.post"),
                            icon="publish",
                            on_click=lambda _e=None, o=occ: _post_occurrence(o),
                        ).props("flat dense color=primary size=sm")

        def _render_subscription_row(ch: SubscriptionCharge) -> None:
            with ui.row().classes(
                f"{HAIRLINE_ROW} w-full items-center justify-between p-2 rounded-lg"
            ):
                with ui.row().classes("items-center gap-2 flex-1"):
                    ui.icon("subscriptions", size="1rem").classes("text-primary")
                    ui.label(ch.name).classes("text-sm font-medium")
                ui.label(f"-{_fmt(ch.amount)}").classes(f"{AMOUNT_EXPENSE} text-sm font-semibold")

        def _select_day(date: datetime.date) -> None:
            """Move the warm tint to ``date`` without redrawing the grid.

            Redrawing would clear ``grid_container`` from inside the click
            handler of a cell that lives in it, and NiceGUI raises once the
            slot a running handler belongs to has been deleted. Two class
            toggles are also cheaper than thirty-one cells.
            """
            cells: dict[datetime.date, ui.element] = state["cells"]
            previous = cells.get(state["selected"])
            if previous is not None:
                previous.classes(remove=CALENDAR_DAY_SELECTED)
            state["selected"] = date
            current = cells.get(date)
            if current is not None:
                current.classes(add=CALENDAR_DAY_SELECTED)

        def _open_day(date: datetime.date, cell: DayAggregate | None) -> None:
            _select_day(date)
            day_header.set_text(t("payment_calendar.day_header", date=date.isoformat()))
            if cell:
                day_totals.set_text(
                    f"{t('payment_calendar.in')}: +{_fmt(cell.inflow)}   "
                    f"{t('payment_calendar.out')}: -{_fmt(cell.outflow)}   "
                    f"{t('payment_calendar.net')}: {_fmt(cell.net)}"
                )
            else:
                day_totals.set_text(t("payment_calendar.day_empty_totals"))

            subs_for_day = state["subs_by_day"].get(date, [])

            day_content.clear()
            with day_content:
                # Overdue items live in the strip above the grid now, where
                # they are visible without opening any day at all.
                ui.label(t("payment_calendar.day_items")).classes(SECTION_TITLE)
                if cell and cell.occurrences:
                    for occ in cell.occurrences:
                        _render_occurrence_row(occ)
                elif not subs_for_day:
                    ui.label(t("payment_calendar.day_empty")).classes(f"{BODY_MUTED} italic")

                if subs_for_day:
                    ui.separator().classes("my-2")
                    ui.label(t("payment_calendar.subscription_charges")).classes(SECTION_TITLE)
                    for ch in subs_for_day:
                        _render_subscription_row(ch)
            day_add_btn.set_text(t("payment_calendar.add_for_day_short", date=date.isoformat()))
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
                        t("payment_calendar.post_all_due"),
                        icon="publish",
                        on_click=_post_all_due,
                    ).props("flat color=primary dense")
                    ui.button(
                        t("payment_calendar.list_view"),
                        icon="list",
                        on_click=lambda: ui.navigate.to("/planned"),
                    ).props("flat color=primary dense")

            # Summary KPIs — the totals the day cells no longer carry
            def _kpi(title: str, value_cls: str) -> ui.label:
                with ui.column().classes(f"{TOOLBAR_CARD} flex-1 min-w-44 gap-0.5"):
                    ui.label(title).classes(SECTION_TITLE)
                    return ui.label("").classes(f"{KPI_VALUE} text-2xl {value_cls}")

            with ui.row().classes("w-full gap-3 flex-wrap items-stretch"):
                kpi_in = _kpi(t("payment_calendar.month_in"), AMOUNT_INCOME)
                kpi_out = _kpi(t("payment_calendar.month_out"), AMOUNT_EXPENSE)
                kpi_net = _kpi(t("payment_calendar.month_net"), AMOUNT_NEUTRAL)
                kpi_overdue = _kpi(t("payment_calendar.overdue_count"), "k-trend--warn")

            # Overdue strip — above the grid, not buried in the day-1 cell
            overdue_strip = ui.column().classes("w-full gap-0")

            # Calendar grid container
            grid_container = ui.column().classes(f"{SECTION_CARD} gap-2")

            async def _refresh() -> None:
                y, m = state["year"], state["month"]
                month_label.set_text(_month_label(y, m))
                last_day = calendar.monthrange(y, m)[1]
                first = datetime.date(y, m, 1)
                last = datetime.date(y, m, last_day)

                async def _load_grid(session: Any) -> tuple[MonthGrid, Any]:
                    overdue_days = _lookback_days()
                    grid = await PlannedTransactionService(session).grid_for_month(
                        y, m, overdue_window_days=overdue_days
                    )
                    sub_sources = await WizardProjectionService(
                        session
                    ).get_payment_calendar_sources(first, last)
                    return grid, sub_sources

                grid, sub_sources = await with_session(_load_grid)
                subs_by_day: dict[datetime.date, list[SubscriptionCharge]] = {}
                for ch in sub_sources.subscription_charges:
                    subs_by_day.setdefault(ch.date, []).append(ch)
                state["subs_by_day"] = subs_by_day

                kpi_in.set_text(f"+{_fmt(grid.total_inflow())}")
                kpi_out.set_text(f"-{_fmt(grid.total_outflow())}")
                net = grid.total_net()
                kpi_net.set_text(f"{'+' if net > 0 else ''}{_fmt(net)}")
                overdue = actually_overdue(grid.overdue, datetime.date.today())
                kpi_overdue.set_text(str(len(overdue)))

                state["grid"] = grid
                _draw_overdue_strip(overdue)
                _draw_grid(grid)

            def _draw_overdue_strip(overdue: list[PlannedOccurrence]) -> None:
                """Everything already late, listed above the month.

                It used to hang off the day-1 cell, which meant an item three
                weeks overdue was invisible until you clicked a day it had
                nothing to do with — and invisible altogether from any other
                month.
                """
                overdue_strip.clear()
                if not overdue:
                    return
                today = datetime.date.today()
                with (
                    overdue_strip,
                    ui.column().classes(f"{WARNING_STRIP} w-full rounded-xl p-4 gap-2"),
                ):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("schedule", size="1rem")
                        ui.label(t("payment_calendar.overdue_title")).classes(SECTION_TITLE)
                    for occ in overdue:
                        _render_overdue_row(occ, today)

            def _render_overdue_row(occ: PlannedOccurrence, today: datetime.date) -> None:
                is_income = occ.type == TransactionType.INCOME
                sign = "+" if is_income else "-"
                amt_cls = AMOUNT_INCOME if is_income else AMOUNT_EXPENSE
                with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                    ui.label(occ.name).classes("text-sm flex-1 min-w-32")
                    ui.label(overdue_age_label(occ.date, today)).classes(f"{MUTED} text-xs")
                    ui.label(f"{sign}{_fmt(abs(occ.amount))}").classes(f"{amt_cls} {MONO} text-sm")
                    ui.button(
                        t("payment_calendar.post"),
                        icon="publish",
                        on_click=lambda _e=None, o=occ: _post_occurrence(o),
                    ).props("flat dense color=primary size=sm")

            def _draw_grid(grid: MonthGrid | None) -> None:
                grid_container.clear()
                if grid is None:
                    return
                y, m = grid.year, grid.month
                first = datetime.date(y, m, 1)
                last_day = calendar.monthrange(y, m)[1]
                # Python: Monday = 0 ... Sunday = 6
                leading = first.weekday()
                total_cells = leading + last_day
                trailing = (7 - total_cells % 7) % 7
                total_cells += trailing

                state["cells"] = {}
                with grid_container:
                    # Weekday header
                    with ui.grid(columns=7).classes("w-full gap-1"):
                        for key in _WEEKDAY_KEYS:
                            ui.label(t(f"payment_calendar.wd_{key}")).classes(
                                f"{SECTION_TITLE} text-center"
                            )

                    # Day cells
                    with ui.grid(columns=7).classes("w-full gap-1"):
                        for idx in range(total_cells):
                            day_num = idx - leading + 1
                            if day_num < 1 or day_num > last_day:
                                ui.element("div").classes(f"{CALENDAR_DAY_BLANK} min-h-20")
                                continue
                            date = datetime.date(y, m, day_num)
                            _draw_day_cell(
                                date=date,
                                cell=grid.days.get(date),
                                is_today=date == datetime.date.today(),
                                is_selected=date == state["selected"],
                            )

            def _draw_day_cell(
                *,
                date: datetime.date,
                cell: DayAggregate | None,
                is_today: bool,
                is_selected: bool,
            ) -> None:
                subs_for_day = state["subs_by_day"].get(date, [])
                marks = day_marks(cell, subs_for_day)

                classes = [CALENDAR_DAY, "min-h-20 p-2 gap-1"]
                if is_today:
                    classes.append(CALENDAR_DAY_TODAY)
                if is_selected:
                    classes.append(CALENDAR_DAY_SELECTED)
                col = ui.column().classes(" ".join(classes))
                col.on("click", lambda _e=None, d=date, c=cell: _open_day(d, c))
                state["cells"][date] = col

                # Three reading levels for the day number and no second tint:
                # today in ink, a working day in muted-strong, a weekend
                # quieter still. Tinting whole weekend columns would stripe
                # the grid and compete with the selected day.
                if is_today:
                    day_cls = f"{INK} font-semibold"
                elif date.weekday() >= 5:
                    day_cls = MUTED
                else:
                    day_cls = CALENDAR_DAY_NUM

                with col:
                    with ui.row().classes("w-full items-center justify-between no-wrap"):
                        ui.label(str(date.day)).classes(f"{MONO} text-base {day_cls}")
                        if is_today:
                            ui.label(t("payment_calendar.today_marker")).classes(
                                f"{SECTION_TITLE} text-[9px]"
                            )

                    if marks.net:
                        tone = AMOUNT_INCOME if marks.net > 0 else AMOUNT_EXPENSE
                        sign = "+" if marks.net > 0 else "-"
                        ui.label(f"{sign}{_fmt(abs(marks.net))}").classes(
                            f"{tone} {MONO} text-sm leading-tight"
                        )

                    if not marks.is_empty:
                        with ui.row().classes("items-center gap-1 flex-wrap mt-auto"):
                            for tone in marks.dots:
                                ui.element("div").classes(f"{CALENDAR_DOT} {tone}")
                            if marks.overflow:
                                ui.label(
                                    t("payment_calendar.more_items", count=marks.overflow)
                                ).classes(f"{MUTED} {MONO} text-[10px] leading-none")

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
