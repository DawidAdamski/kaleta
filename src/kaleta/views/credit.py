"""Credit module — dedicated view for cards and loans."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.credit import (
    CardView,
    CreditCardProfileCreate,
    CreditStatus,
    LoanProfileCreate,
    LoanView,
)
from kaleta.services import AccountService, CreditService
from kaleta.services.credit_service import amortisation_schedule
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
)

_STATUS_COLOR: dict[CreditStatus, str] = {
    CreditStatus.ON_TIME: "positive",
    CreditStatus.GRACE: "amber-7",
    CreditStatus.OVERDUE: "negative",
}


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def _fmt_date(d: datetime.date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _utilization_color(pct: Decimal) -> str:
    if pct >= Decimal("0.7"):
        return "negative"
    if pct >= Decimal("0.3"):
        return "amber-7"
    return "positive"


def register() -> None:
    @ui.page("/credit")
    async def credit_page() -> None:
        async with AsyncSessionFactory() as session:
            svc = CreditService(session)
            cards = await svc.list_cards()
            loans = await svc.list_loans()

        with page_layout(t("credit.title"), wide=True):
            with ui.column().classes("gap-1"):
                ui.label(t("credit.title")).classes(PAGE_TITLE)
                ui.label(t("credit.subtitle")).classes(BODY_MUTED)

            # ── Tabs: Cards | Loans ──────────────────────────────────────
            with ui.tabs().classes("w-full") as tabs:
                cards_tab = ui.tab(
                    "cards", label=t("credit.tab_cards"), icon="credit_card"
                )
                loans_tab = ui.tab(
                    "loans", label=t("credit.tab_loans"), icon="account_balance"
                )

            with ui.tab_panels(tabs, value=cards_tab).classes("w-full"):
                with ui.tab_panel(cards_tab):
                    await _render_cards_tab(cards)
                with ui.tab_panel(loans_tab):
                    await _render_loans_tab(loans)


# ── Cards tab ────────────────────────────────────────────────────────────────


async def _render_cards_tab(cards: list[CardView]) -> None:
    # ── Add-card dialog ──────────────────────────────────────────────────
    with ui.dialog() as add_card_dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label(t("credit.new_card_title")).classes("text-lg font-bold")

        name_in = ui.input(label=t("credit.field_name")).props("dense outlined").classes("w-full")
        with ui.row().classes("w-full gap-2"):
            limit_in = (
                ui.number(
                    label=t("credit.field_credit_limit"), value=0, min=0, format="%.2f"
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            balance_in = (
                ui.number(
                    label=t("credit.field_current_balance"),
                    value=0,
                    min=0,
                    format="%.2f",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
        with ui.row().classes("w-full gap-2"):
            statement_day_in = (
                ui.number(
                    label=t("credit.field_statement_day"),
                    value=1,
                    min=1,
                    max=28,
                    format="%d",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            due_day_in = (
                ui.number(
                    label=t("credit.field_payment_due_day"),
                    value=25,
                    min=1,
                    max=28,
                    format="%d",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
        with ui.row().classes("w-full gap-2"):
            apr_in = (
                ui.number(
                    label=t("credit.field_apr"),
                    value=0,
                    min=0,
                    max=100,
                    format="%.2f",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            floor_in = (
                ui.number(
                    label=t("credit.field_min_floor"),
                    value=30,
                    min=0,
                    format="%.2f",
                )
                .props("dense outlined")
                .classes("flex-1")
            )

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=add_card_dialog.close).props("flat")
            save_card_btn = ui.button(
                t("common.save"), icon="check"
            ).props("color=primary unelevated")

    async def _save_card() -> None:
        try:
            name = (name_in.value or "").strip()
            if not name:
                ui.notify(t("credit.err_name_required"), type="warning")
                return
            limit = Decimal(str(limit_in.value or 0))
            if limit <= 0:
                ui.notify(t("credit.err_limit_required"), type="warning")
                return
            balance = Decimal(str(balance_in.value or 0))
            apr = Decimal(str(apr_in.value or 0))
            floor = Decimal(str(floor_in.value or 0))
        except (ValueError, TypeError) as exc:
            ui.notify(str(exc), type="negative")
            return

        async with AsyncSessionFactory() as s:
            # Account stores the balance as *negative* when money is owed.
            account = await AccountService(s).create(
                AccountCreate(
                    name=name,
                    type=AccountType.CREDIT,
                    balance=-balance,
                )
            )
            await CreditService(s).create_card(
                CreditCardProfileCreate(
                    account_id=account.id,
                    credit_limit=limit,
                    statement_day=int(statement_day_in.value or 1),
                    payment_due_day=int(due_day_in.value or 25),
                    apr=apr,
                    min_payment_floor=floor,
                )
            )
        add_card_dialog.close()
        ui.notify(t("credit.card_saved"), type="positive")
        ui.navigate.reload()

    save_card_btn.on_click(_save_card)

    with ui.row().classes("w-full justify-end"):
        ui.button(
            t("credit.new_card"),
            icon="add",
            on_click=add_card_dialog.open,
        ).props("color=primary unelevated size=sm")

    if not cards:
        with ui.card().classes(SECTION_CARD):
            ui.label(t("credit.cards_empty")).classes(f"{BODY_MUTED} py-2")
        return

    for c in cards:
        _render_card(c)


def _render_card(card: CardView) -> None:
    colour = _utilization_color(card.utilization_pct)
    status_colour = _STATUS_COLOR[card.status]
    pct_clamped = min(float(card.utilization_pct), 1.0)

    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("credit_card", size="1.6rem").classes("text-primary")
                with ui.column().classes("gap-0"):
                    ui.label(card.account_name).classes("text-lg font-semibold")
                    ui.label(
                        t(
                            "credit.card_subtitle",
                            balance=_fmt(card.current_balance),
                            limit=_fmt(card.credit_limit),
                            currency=card.currency,
                        )
                    ).classes(BODY_MUTED)
            with ui.column().classes("items-end gap-0"):
                pct_label = int(round(float(card.utilization_pct) * 100))
                ui.label(f"{pct_label}%").classes(
                    f"text-lg font-bold text-{colour}"
                )
                ui.label(t("credit.card_utilization")).classes(
                    "text-xs text-slate-500"
                )

        ui.linear_progress(
            value=pct_clamped, size="8px", show_value=False, color=colour
        ).classes("w-full mt-3")

        with ui.row().classes("w-full items-center justify-between mt-3"):
            with ui.column().classes("gap-0"):
                ui.label(t("credit.next_due_label")).classes(
                    "text-xs text-slate-500 uppercase tracking-wide"
                )
                ui.label(_fmt_date(card.next_due_at)).classes("text-sm font-semibold")
            with ui.column().classes("gap-0 items-end"):
                ui.label(t("credit.min_payment_label")).classes(
                    "text-xs text-slate-500 uppercase tracking-wide"
                )
                ui.label(
                    f"{_fmt(card.min_payment)} {card.currency}"
                ).classes(f"{AMOUNT_EXPENSE} text-sm font-semibold")
            ui.chip(
                t(f"credit.status_{card.status.value}"), color=status_colour
            ).props("dense outline")


# ── Loans tab ────────────────────────────────────────────────────────────────


async def _render_loans_tab(loans: list[LoanView]) -> None:
    # ── Add-loan dialog ──────────────────────────────────────────────────
    with ui.dialog() as add_loan_dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label(t("credit.new_loan_title")).classes("text-lg font-bold")
        l_name_in = (
            ui.input(label=t("credit.field_name")).props("dense outlined").classes("w-full")
        )
        with ui.row().classes("w-full gap-2"):
            l_principal_in = (
                ui.number(
                    label=t("credit.field_principal"), value=0, min=0, format="%.2f"
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            l_apr_in = (
                ui.number(
                    label=t("credit.field_apr"), value=0, min=0, max=100, format="%.2f"
                )
                .props("dense outlined")
                .classes("flex-1")
            )
        with ui.row().classes("w-full gap-2"):
            l_term_in = (
                ui.number(
                    label=t("credit.field_term_months"),
                    value=60,
                    min=1,
                    max=600,
                    format="%d",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            l_start_in = (
                ui.input(label=t("credit.field_start_date"))
                .props("dense outlined type=date")
                .classes("flex-1")
            )

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=add_loan_dialog.close).props("flat")
            save_loan_btn = ui.button(
                t("common.save"), icon="check"
            ).props("color=primary unelevated")

    async def _save_loan() -> None:
        try:
            name = (l_name_in.value or "").strip()
            if not name:
                ui.notify(t("credit.err_name_required"), type="warning")
                return
            principal = Decimal(str(l_principal_in.value or 0))
            if principal <= 0:
                ui.notify(t("credit.err_principal_required"), type="warning")
                return
            apr = Decimal(str(l_apr_in.value or 0))
            term = int(l_term_in.value or 1)
            start = datetime.date.fromisoformat(
                l_start_in.value or datetime.date.today().isoformat()
            )
        except (ValueError, TypeError) as exc:
            ui.notify(str(exc), type="negative")
            return

        async with AsyncSessionFactory() as s:
            account = await AccountService(s).create(
                AccountCreate(
                    name=name,
                    type=AccountType.CREDIT,
                    balance=-principal,
                )
            )
            await CreditService(s).create_loan(
                LoanProfileCreate(
                    account_id=account.id,
                    principal=principal,
                    apr=apr,
                    term_months=term,
                    start_date=start,
                )
            )
        add_loan_dialog.close()
        ui.notify(t("credit.loan_saved"), type="positive")
        ui.navigate.reload()

    save_loan_btn.on_click(_save_loan)

    with ui.row().classes("w-full justify-end"):
        ui.button(
            t("credit.new_loan"),
            icon="add",
            on_click=add_loan_dialog.open,
        ).props("color=primary unelevated size=sm")

    if not loans:
        with ui.card().classes(SECTION_CARD):
            ui.label(t("credit.loans_empty")).classes(f"{BODY_MUTED} py-2")
        return

    for ln in loans:
        _render_loan(ln)


def _render_loan(loan: LoanView) -> None:
    status_colour = _STATUS_COLOR[loan.status]
    pct_clamped = (
        float(loan.months_elapsed / loan.term_months)
        if loan.term_months > 0
        else 0.0
    )

    with ui.card().classes(SECTION_CARD):
        with ui.row().classes("w-full items-center justify-between gap-3"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("account_balance", size="1.6rem").classes("text-primary")
                with ui.column().classes("gap-0"):
                    ui.label(loan.account_name).classes("text-lg font-semibold")
                    ui.label(
                        t(
                            "credit.loan_subtitle",
                            principal=_fmt(loan.principal),
                            apr=_fmt(loan.apr),
                            term=loan.term_months,
                            currency=loan.currency,
                        )
                    ).classes(BODY_MUTED)
            with ui.column().classes("items-end gap-0"):
                ui.label(
                    t(
                        "credit.loan_monthly_payment",
                        amount=_fmt(loan.monthly_payment),
                        currency=loan.currency,
                    )
                ).classes("text-base font-bold")
                ui.label(
                    t(
                        "credit.loan_remaining",
                        amount=_fmt(loan.remaining_balance),
                        currency=loan.currency,
                    )
                ).classes("text-xs text-slate-500")

        ui.linear_progress(
            value=pct_clamped, size="8px", show_value=False, color="primary"
        ).classes("w-full mt-3")

        with ui.row().classes("w-full items-center justify-between mt-3"):
            with ui.column().classes("gap-0"):
                ui.label(t("credit.next_due_label")).classes(
                    "text-xs text-slate-500 uppercase tracking-wide"
                )
                ui.label(_fmt_date(loan.next_due_at)).classes("text-sm font-semibold")
            with ui.column().classes("gap-0 items-end"):
                ui.label(t("credit.loan_progress_label")).classes(
                    "text-xs text-slate-500 uppercase tracking-wide"
                )
                ui.label(
                    t(
                        "credit.loan_progress",
                        elapsed=loan.months_elapsed,
                        total=loan.term_months,
                    )
                ).classes("text-sm font-semibold")
            ui.chip(
                t(f"credit.status_{loan.status.value}"), color=status_colour
            ).props("dense outline")

        # Amortisation expansion — first 6 rows preview.
        from kaleta.models.credit import LoanProfile

        dummy = LoanProfile(
            account_id=loan.account_id,
            principal=loan.principal,
            apr=loan.apr,
            term_months=loan.term_months,
            start_date=loan.start_date,
            monthly_payment=loan.monthly_payment,
        )
        schedule = amortisation_schedule(dummy)
        with ui.expansion(t("credit.loan_schedule"), icon="list_alt").classes(
            "w-full mt-3"
        ).props("dense"):
            _render_schedule_preview(schedule, currency=loan.currency)


def _render_schedule_preview(
    schedule: list[Any], *, currency: str, preview_rows: int = 6
) -> None:
    if not schedule:
        return
    # Header row
    with ui.row().classes(
        "w-full px-2 py-1 text-xs text-slate-500 font-medium border-b"
    ):
        ui.label(t("credit.sched_month")).classes("w-16")
        ui.label(t("credit.sched_date")).classes("w-28")
        ui.label(t("credit.sched_payment")).classes("flex-1 text-right")
        ui.label(t("credit.sched_principal")).classes("flex-1 text-right")
        ui.label(t("credit.sched_interest")).classes("flex-1 text-right")
        ui.label(t("credit.sched_remaining")).classes("flex-1 text-right")

    rows_to_show = schedule[: preview_rows]
    for row in rows_to_show:
        with ui.row().classes("w-full px-2 py-1 border-b border-slate-200/20"):
            ui.label(str(row.month)).classes("w-16 text-sm text-slate-500")
            ui.label(_fmt_date(row.date)).classes("w-28 text-sm")
            ui.label(f"{_fmt(row.payment)} {currency}").classes(
                "flex-1 text-right text-sm"
            )
            ui.label(_fmt(row.principal_paid)).classes(
                "flex-1 text-right text-sm"
            )
            ui.label(_fmt(row.interest_paid)).classes(
                "flex-1 text-right text-sm text-slate-500"
            )
            ui.label(_fmt(row.remaining_principal)).classes(
                "flex-1 text-right text-sm"
            )
    if len(schedule) > preview_rows:
        ui.label(
            t("credit.sched_and_more", count=len(schedule) - preview_rows)
        ).classes(f"{BODY_MUTED} text-xs px-2 py-1")
