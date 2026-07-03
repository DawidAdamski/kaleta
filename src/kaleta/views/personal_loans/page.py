"""Personal loans page — routing, layout, and section wiring."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.personal_loan import LoanStatus
from kaleta.services import AccountService, CategoryService, PersonalLoanService, with_session
from kaleta.views.components.amount_label import amount_css_class
from kaleta.views.layout import page_layout
from kaleta.views.personal_loans.dialogs import build_personal_loan_dialogs
from kaleta.views.personal_loans.helpers import fmt_amount
from kaleta.views.personal_loans.rows import render_loan_row
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING


async def personal_loans_page() -> None:
    async def _load_page_data(session: Any) -> tuple[Any, ...]:
        svc = PersonalLoanService(session)
        loans = await svc.list_loans()
        counterparties = await svc.list_counterparties()
        totals = await svc.totals()
        accounts = await AccountService(session).list()
        all_cats = await CategoryService(session).list()
        return loans, counterparties, totals, accounts, all_cats

    loans, counterparties, totals, accounts, all_cats = await with_session(_load_page_data)

    counterparty_opts: dict[int, str] = {c.id: c.name for c in counterparties}
    account_opts: dict[int, str] = {a.id: a.name for a in accounts}
    expense_cat_opts = CategoryService.build_option_labels(
        [c for c in all_cats if c.type.value == "expense"]
    )
    income_cat_opts = CategoryService.build_option_labels(
        [c for c in all_cats if c.type.value == "income"]
    )

    with page_layout(t("personal_loans.title"), wide=True):
        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(t("personal_loans.title")).classes(PAGE_TITLE)
                ui.label(t("personal_loans.subtitle")).classes(BODY_MUTED)
            with ui.row().classes("items-center gap-4"):
                income_cls = amount_css_class("income")
                expense_cls = amount_css_class("expense")
                with ui.column().classes("items-end gap-0"):
                    ui.label(t("personal_loans.they_owe_you")).classes(
                        "text-xs text-slate-500 uppercase tracking-wide"
                    )
                    ui.label(fmt_amount(totals.they_owe_you)).classes(
                        f"{income_cls} text-lg font-bold"
                    )
                with ui.column().classes("items-end gap-0"):
                    ui.label(t("personal_loans.you_owe")).classes(
                        "text-xs text-slate-500 uppercase tracking-wide"
                    )
                    ui.label(fmt_amount(totals.you_owe)).classes(f"{expense_cls} text-lg font-bold")

        (
            open_add_loan,
            open_edit_loan,
            open_delete_dialog,
            open_repayment_dialog,
            delete_repayment,
        ) = build_personal_loan_dialogs(
            counterparty_opts=counterparty_opts,
            account_opts=account_opts,
            expense_cat_opts=expense_cat_opts,
            income_cat_opts=income_cat_opts,
        )

        with ui.row().classes("w-full justify-end"):
            ui.button(t("personal_loans.add"), icon="add", on_click=open_add_loan).props(
                "color=primary unelevated size=sm"
            )

        outstanding = [ln for ln in loans if ln.status == LoanStatus.OUTSTANDING]
        settled = [ln for ln in loans if ln.status == LoanStatus.SETTLED]

        if not loans:
            with ui.card().classes(SECTION_CARD):
                ui.label(t("personal_loans.empty")).classes(f"{BODY_MUTED} py-2")

        if outstanding:
            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("items-center gap-2"):
                    ui.label(t("personal_loans.section_outstanding")).classes(SECTION_HEADING)
                    ui.badge(
                        t(
                            "personal_loans.outstanding_count",
                            count=totals.outstanding_count,
                        )
                    ).props("color=amber-7 rounded")
                for loan in outstanding:
                    render_loan_row(
                        loan,
                        on_edit=open_edit_loan,
                        on_delete=open_delete_dialog,
                        on_repayment=open_repayment_dialog,
                        on_rep_delete=delete_repayment,
                    )

        if settled:
            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("items-center gap-2"):
                    ui.label(t("personal_loans.section_settled")).classes(SECTION_HEADING)
                    ui.badge(
                        t(
                            "personal_loans.settled_count",
                            count=totals.settled_count,
                        )
                    ).props("color=positive rounded")
                for loan in settled:
                    render_loan_row(
                        loan,
                        on_edit=open_edit_loan,
                        on_delete=open_delete_dialog,
                        on_repayment=open_repayment_dialog,
                        on_rep_delete=delete_repayment,
                    )
