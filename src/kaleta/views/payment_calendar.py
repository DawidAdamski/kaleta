# SPDX-License-Identifier: AGPL-3.0-or-later
"""Payment Calendar — month-grid view of planned transactions.

Each cell shows the day's net and one dot per thing happening on it; the
month's totals live in the KPI row above, where there is room for them.
Clicking a cell tints it and opens a side-sheet with the day's occurrences
and a Quick Add form. Everything already late is listed in a strip above the
grid, visible from any month without opening a day.

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
    ACCENT_TEXT,
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    AMOUNT_NEUTRAL,
    BODY_MUTED,
    BUTTON_INK,
    CALENDAR_DAY,
    CALENDAR_DAY_BLANK,
    CALENDAR_DAY_NUM,
    CALENDAR_DAY_SELECTED,
    CALENDAR_DAY_TODAY,
    CALENDAR_DOT,
    CALENDAR_DOT_FLAT,
    CALENDAR_DOT_IN,
    CALENDAR_DOT_OUT,
    CARD_TITLE,
    DAY_ITEM,
    DAY_PANEL,
    DAY_PANEL_FOOT,
    INK,
    MONO,
    MUTED,
    OVERDUE_AMOUNT,
    OVERDUE_RULE,
    OVERDUE_STRIP,
    OVERDUE_TEXT,
    PAGE_EYEBROW,
    PAGE_TITLE,
    RAIL_EYEBROW,
    SECTION_CARD,
    SECTION_TITLE,
    STAT_CARD,
    STAT_CARD_FIGURE,
    STAT_CARD_SM,
    STAT_CARD_WARM,
    STAT_FIGURE_SM,
    TITLE_ACTION,
    TITLE_ACTION_PRIMARY,
    WARM_ACCENT,
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


def occurrence_amount(occ: PlannedOccurrence) -> tuple[str, str]:
    """The amount as it should be read: ``("+210.00", tone class)``.

    A transfer moves money between the user's own accounts, so it gets a
    bare figure in the neutral tone — the same rule the day cell's dots
    follow. Signing it as an expense would say money left, which it did not.
    """
    if occ.type == TransactionType.INCOME:
        return f"+{_fmt(abs(occ.amount))}", AMOUNT_INCOME
    if occ.type == TransactionType.EXPENSE:
        return f"-{_fmt(abs(occ.amount))}", AMOUNT_EXPENSE
    return _fmt(abs(occ.amount)), AMOUNT_NEUTRAL


def overdue_age_label(occ_date: datetime.date, today: datetime.date) -> str:
    """ "3 days" — how long the item has been waiting, in Polish-aware plurals."""
    days = (today - occ_date).days
    return t(plural_key("payment_calendar.overdue_age", days), days=days)


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", " ")


def _fmt_cell(amount: Decimal) -> str:
    """A day cell's figure: no pennies unless there are any.

    Thirty-one cells in a grid are read by comparing them down a column, and
    ",00" on every one of them is three characters of noise in a box nine
    pixels wide. Artboard `3c` writes "+9 240" and "−23,99" side by side.
    """
    whole = amount == amount.to_integral_value()
    body = f"{amount:,.0f}" if whole else f"{amount:,.2f}"
    return body.replace(",", " ")


def _add_months(d: datetime.date, months: int) -> datetime.date:
    total = d.month + months
    year = d.year + (total - 1) // 12
    month = (total - 1) % 12 + 1
    return datetime.date(year, month, 1)


def _month_label(year: int, month: int) -> str:
    return f"{t(f'payment_calendar.month_{month}')} {year}"


def _day_title(date: datetime.date) -> str:
    """ "Tuesday 15 September" — the sheet's own heading."""
    weekday = t(f"payment_calendar.wd_full_{_WEEKDAY_KEYS[date.weekday()]}")
    return t(
        "payment_calendar.day_title",
        weekday=weekday,
        day=date.day,
        month=t(f"common.month_of_{date.month}"),
    )


def _day_short(date: datetime.date) -> str:
    return f"{date.day:02d}.{date.month:02d}"


def _in(cell: DayAggregate | None) -> Decimal:
    return cell.inflow if cell else Decimal("0")


def _out(cell: DayAggregate | None) -> Decimal:
    return cell.outflow if cell else Decimal("0")


def _net(cell: DayAggregate | None) -> Decimal:
    return cell.net if cell else Decimal("0")


def _signed(amount: Decimal, sign: str) -> str:
    """ "+1 830,00", or a bare "0.00" — nothing moved in either direction."""
    return f"{sign}{_fmt(amount)}" if amount else _fmt(amount)


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
            # The day sheet starts open on today, which is the day the page
            # is almost always opened to look at.
            "panel_open": True,
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
            await _refresh()

        async def _post_overdue(overdue: list[PlannedOccurrence]) -> None:
            """Post exactly the items the strip is listing, and nothing else.

            Not `post_due`: that posts everything due up to today, including
            items dated today that the strip does not list - and a button
            labelled with the strip's own count would then have posted more
            than it counted.
            """
            posted = 0
            for occ in list(overdue):
                try:

                    async def _run(session: Any, o: PlannedOccurrence = occ) -> None:
                        await PlannedTransactionService(session).post_occurrence(
                            o.planned_id, o.date
                        )

                    await with_session(_run)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    continue
                posted += 1
            if posted:
                ui.notify(t("payment_calendar.posted_all", count=posted), type="positive")
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
            amount, amt_cls = occurrence_amount(occ)
            can_post = occ.date <= datetime.date.today()
            with ui.element("div").classes(f"{DAY_ITEM} w-full" + (" opacity-70" if muted else "")):
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label(occ.name).classes(f"{INK} text-[13.5px] font-medium truncate")
                    sub_parts = [occ.account_name]
                    if occ.category_name:
                        sub_parts.append(occ.category_name)
                    ui.label(" · ".join(sub_parts)).classes(
                        f"{MUTED} text-[11.5px] mt-0.5 truncate"
                    )
                ui.label(amount).classes(f"{amt_cls} {MONO} text-[13.5px] font-semibold")
                if can_post:
                    # Artboard `3c` draws the row without it; an item that is
                    # due and cannot be posted from the sheet it is listed in
                    # would send the reader back to the strip to do it.
                    ui.button(
                        icon="publish",
                        on_click=lambda _e=None, o=occ: _post_occurrence(o),
                    ).props("flat dense round size=sm color=primary").tooltip(
                        t("payment_calendar.post")
                    )

        def _render_subscription_row(ch: SubscriptionCharge) -> None:
            with ui.element("div").classes(f"{DAY_ITEM} w-full"):
                ui.icon("subscriptions", size="17px").classes(f"{ACCENT_TEXT} flex-none")
                with ui.column().classes("gap-0 flex-1 min-w-0"):
                    ui.label(ch.name).classes(f"{INK} text-[13.5px] font-medium truncate")
                    ui.label(t("payment_calendar.subscription_charges")).classes(
                        f"{MUTED} text-[11.5px] mt-0.5"
                    )
                ui.label(f"-{_fmt(ch.amount)}").classes(
                    f"{AMOUNT_EXPENSE} {MONO} text-[13.5px] font-semibold"
                )

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
            state["panel_open"] = True
            _draw_day_panel(date, cell)

        def _close_day_panel() -> None:
            state["panel_open"] = False
            day_panel.set_visibility(False)

        def _draw_day_panel(date: datetime.date, cell: DayAggregate | None) -> None:
            """The picked day beside the month, not a drawer over it.

            A sheet that slid in from the right covered the grid it was
            about, so the one comparison the screen exists for — this day
            against the ones around it — could not be made while it was open.
            """
            day_panel.set_visibility(bool(state["panel_open"]))
            day_panel.clear()
            if not state["panel_open"]:
                return
            subs_for_day = state["subs_by_day"].get(date, [])
            with day_panel:
                with ui.row().classes("w-full items-baseline justify-between gap-3 no-wrap"):
                    ui.label(_day_title(date)).classes(CARD_TITLE)
                    ui.icon("close", size="19px").classes(f"{MUTED} cursor-pointer").on(
                        "click", _close_day_panel
                    ).tooltip(t("payment_calendar.day_sheet_close"))
                with ui.row().classes("w-full gap-[18px] mt-2.5 pb-4 flex-wrap k-hairline-bottom"):
                    _day_total(t("payment_calendar.in"), _signed(_in(cell), "+"), AMOUNT_INCOME)
                    _day_total(t("payment_calendar.out"), _signed(_out(cell), "-"), AMOUNT_EXPENSE)
                    _day_total(t("payment_calendar.net"), _fmt(_net(cell)), AMOUNT_NEUTRAL)

                # Overdue items live in the strip above the grid now, where
                # they are visible without opening any day at all.
                ui.label(t("payment_calendar.day_planned")).classes(f"{RAIL_EYEBROW} mt-4 mb-2.5")
                if cell and cell.occurrences:
                    with ui.column().classes("w-full gap-[9px]"):
                        for occ in cell.occurrences:
                            _render_occurrence_row(occ)
                elif not subs_for_day:
                    ui.label(t("payment_calendar.day_empty")).classes(BODY_MUTED)

                if subs_for_day:
                    ui.label(t("payment_calendar.subscription_charges")).classes(
                        f"{RAIL_EYEBROW} mt-5 mb-2.5"
                    )
                    with ui.column().classes("w-full gap-[9px]"):
                        for ch in subs_for_day:
                            _render_subscription_row(ch)

                # One button, not the artboard's two: its "Post this day"
                # would be a new action, and every item in the sheet already
                # carries the one that posts it.
                with ui.row().classes(f"{DAY_PANEL_FOOT} w-full gap-[9px] no-wrap"):
                    ui.button(
                        t("payment_calendar.add_for_day_short", date=_day_short(date)),
                        on_click=lambda d=date: _open_quick_add(d),
                        color=None,
                    ).props("flat dense no-caps").classes(f"{BUTTON_INK} flex-1")

        def _day_total(label: str, figure: str, tone: str) -> None:
            with ui.row().classes("items-baseline gap-1.5 no-wrap"):
                ui.label(label).classes(f"{MUTED} text-[12px]")
                ui.label(figure).classes(f"{tone} {MONO} text-[12px]")

        # ── Main layout ──────────────────────────────────────────────────────
        with page_layout(t("payment_calendar.title"), wide=True):
            # The month is the title: artboard `3c` names the screen once, in
            # the drawer and the header, and gives the page's own big type to
            # the thing the arrows either side of it change.
            with ui.row().classes("w-full items-end justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-0 min-w-0"):
                    ui.label(t("payment_calendar.eyebrow")).classes(PAGE_EYEBROW).props(
                        "data-page-eyebrow"
                    )
                    with ui.row().classes("items-center gap-3.5 no-wrap"):
                        ui.icon("chevron_left", size="22px").classes(f"{INK} cursor-pointer").on(
                            "click", lambda: _shift_month(-1)
                        ).tooltip(t("payment_calendar.prev_month"))
                        month_label = ui.label(_month_label(state["year"], state["month"])).classes(
                            PAGE_TITLE
                        )
                        ui.icon("chevron_right", size="22px").classes(f"{INK} cursor-pointer").on(
                            "click", lambda: _shift_month(1)
                        ).tooltip(t("payment_calendar.next_month"))
                with ui.row().classes("items-center gap-[9px]"):
                    ui.button(
                        t("payment_calendar.today"),
                        icon="today",
                        on_click=lambda: _goto(today.year, today.month),
                        color=None,
                    ).props("flat no-caps dense").classes(TITLE_ACTION)
                    ui.button(
                        t("payment_calendar.list_view"),
                        icon="list",
                        on_click=lambda: ui.navigate.to("/planned"),
                        color=None,
                    ).props("flat no-caps dense").classes(TITLE_ACTION)
                    ui.button(
                        t("payment_calendar.post_all_due"),
                        icon="publish",
                        on_click=_post_all_due,
                        color=None,
                    ).props("flat no-caps dense").classes(TITLE_ACTION_PRIMARY)

            # Summary KPIs — the totals the day cells no longer carry
            def _kpi(title: str, value_cls: str, *, warm: bool = False) -> ui.label:
                surface = STAT_CARD_WARM if warm else STAT_CARD
                with ui.column().classes(f"{surface} {STAT_CARD_SM} gap-0"):
                    ui.label(title).classes(RAIL_EYEBROW if warm else "k-eyebrow")
                    if not warm:
                        return ui.label("").classes(
                            f"{STAT_CARD_FIGURE} {STAT_FIGURE_SM} {value_cls}"
                        )
                    # The overdue card is not a figure to read but a thing to
                    # do something about, so the count carries its own words.
                    with ui.row().classes("items-baseline gap-2"):
                        figure = ui.label("").classes(
                            f"{STAT_CARD_FIGURE} {STAT_FIGURE_SM} {value_cls}"
                        )
                        ui.label(t("payment_calendar.overdue_hint")).classes(
                            f"{value_cls} text-[12px]"
                        )
                    return figure

            with ui.row().classes("w-full gap-[18px] flex-wrap items-stretch"):
                kpi_in = _kpi(t("payment_calendar.month_in"), AMOUNT_INCOME)
                kpi_out = _kpi(t("payment_calendar.month_out"), AMOUNT_EXPENSE)
                kpi_net = _kpi(t("payment_calendar.month_net"), AMOUNT_NEUTRAL)
                kpi_overdue = _kpi(t("payment_calendar.overdue_count"), WARM_ACCENT, warm=True)

            # Overdue strip — above the grid, not buried in the day-1 cell
            overdue_strip = ui.column().classes("w-full gap-0")

            # The month and the day you picked out of it, side by side.
            with ui.row().classes("w-full gap-5 items-start no-wrap"):
                grid_container = ui.column().classes(f"{SECTION_CARD} flex-1 min-w-0 gap-0 !p-5")
                day_panel = ui.column().classes(f"{SECTION_CARD} {DAY_PANEL} gap-0")

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
                selected: datetime.date = state["selected"]
                _draw_day_panel(selected, grid.days.get(selected))

            def _draw_overdue_strip(overdue: list[PlannedOccurrence]) -> None:
                """Everything already late, on one line above the month.

                It used to hang off the day-1 cell, which meant an item three
                weeks overdue was invisible until you clicked a day it had
                nothing to do with — and invisible altogether from any other
                month. Artboard `3c` reads it as a sentence rather than a
                list: what is late, since when, for how much, and one button
                that clears the lot.
                """
                overdue_strip.clear()
                if not overdue:
                    return
                with overdue_strip, ui.row().classes(f"{OVERDUE_STRIP} w-full"):
                    ui.icon("error_outline", size="19px").classes("flex-none")
                    for index, occ in enumerate(overdue):
                        if index:
                            ui.element("span").classes(OVERDUE_RULE)
                        _render_overdue_item(occ)
                    ui.space()
                    ui.button(
                        t("payment_calendar.post_n", count=len(overdue)),
                        on_click=lambda _e=None, items=list(overdue): _post_overdue(items),
                        color=None,
                    ).props("flat dense no-caps").classes(BUTTON_INK)

            def _render_overdue_item(occ: PlannedOccurrence) -> None:
                amount, _amt_cls = occurrence_amount(occ)
                when = f"{occ.date.day:02d}.{occ.date.month:02d}"
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.label(t("payment_calendar.overdue_since", date=when, name=occ.name)).classes(
                        OVERDUE_TEXT
                    )
                    ui.label(amount).classes(OVERDUE_AMOUNT)

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
                    with ui.grid(columns=7).classes("w-full mb-2.5").style("gap:8px"):
                        for key in _WEEKDAY_KEYS:
                            ui.label(t(f"payment_calendar.wd_{key}")).classes(
                                f"{SECTION_TITLE} text-center text-[9.5px]"
                            )

                    # Day cells
                    with ui.grid(columns=7).classes("w-full").style("gap:8px"):
                        for idx in range(total_cells):
                            day_num = idx - leading + 1
                            if day_num < 1 or day_num > last_day:
                                ui.element("div").classes(f"{CALENDAR_DAY_BLANK} min-h-[84px]")
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

                classes = [CALENDAR_DAY, "min-h-[84px] px-[9px] py-2 gap-0"]
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
                        ui.label(str(date.day)).classes(f"{MONO} text-sm {day_cls}")
                        if is_today:
                            ui.label(t("payment_calendar.today_marker")).classes(
                                f"{SECTION_TITLE} text-[9px]"
                            )

                    if marks.net:
                        tone = AMOUNT_INCOME if marks.net > 0 else AMOUNT_EXPENSE
                        sign = "+" if marks.net > 0 else "-"
                        ui.label(f"{sign}{_fmt_cell(abs(marks.net))}").classes(
                            f"{tone} {MONO} text-xs leading-tight mt-1.5"
                        )

                    if not marks.is_empty:
                        with ui.row().classes("items-center gap-[3px] flex-wrap mt-1.5"):
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
                # The sheet is about a day in the month on screen; paging
                # away from it without moving the selection would leave it
                # describing a day nobody can see.
                state["selected"] = new_first
                ui.timer(0.01, _refresh, once=True)

            def _goto(year: int, month: int) -> None:
                state["year"] = year
                state["month"] = month
                ui.timer(0.01, _refresh, once=True)

            await _refresh()
