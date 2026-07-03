"""Personal loan list row renderers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.personal_loan import LoanDirection, LoanStatus
from kaleta.services.personal_loan_service import compute_remaining
from kaleta.views.components.amount_label import amount_css_class
from kaleta.views.personal_loans.helpers import fmt_amount, fmt_date, notes_preview
from kaleta.views.theme import BODY_MUTED


def render_loan_row(
    loan: Any,
    *,
    on_edit: Callable[[Any], None],
    on_delete: Callable[[int], None],
    on_repayment: Callable[[int], None],
    on_rep_delete: Callable[[int], Awaitable[None]],
) -> None:
    repaid_amounts = [r.amount for r in loan.repayments]
    remaining = compute_remaining(loan.principal, repaid_amounts)
    is_outgoing = loan.direction == LoanDirection.OUTGOING
    amount_cls = amount_css_class("income" if is_outgoing else "expense")
    icon = "arrow_outward" if is_outgoing else "arrow_downward"

    is_settled = loan.status == LoanStatus.SETTLED
    row_opacity = " opacity-75" if is_settled else ""

    with ui.element("div").classes(
        f"w-full mt-3 p-3 rounded border border-slate-200/30{row_opacity}"
    ):
        with ui.row().classes("w-full items-center gap-3"):
            ui.icon(icon, size="1.2rem").classes(amount_cls)
            with ui.column().classes("flex-1 gap-0"):
                ui.label(loan.counterparty.name).classes("text-base font-semibold")
                _loan_row_subtitle(loan)
            with ui.column().classes("items-end gap-0"):
                if is_settled:
                    ui.label(
                        t(
                            "personal_loans.row_principal",
                            amount=fmt_amount(loan.principal),
                            currency=loan.currency,
                        )
                    ).classes(f"{BODY_MUTED} text-sm")
                else:
                    ui.label(
                        t(
                            "personal_loans.row_remaining",
                            amount=fmt_amount(remaining),
                            currency=loan.currency,
                        )
                    ).classes(f"{amount_cls} text-base font-bold")
                    ui.label(
                        t(
                            "personal_loans.row_principal",
                            amount=fmt_amount(loan.principal),
                            currency=loan.currency,
                        )
                    ).classes("text-xs text-slate-500")
            ui.button(icon="edit", on_click=lambda _e, ll=loan: on_edit(ll)).props(
                "flat dense round color=grey-7"
            ).tooltip(t("personal_loans.action_edit"))
            if not is_settled:
                ui.button(
                    icon="payments",
                    on_click=lambda _e, lid=loan.id: on_repayment(lid),
                ).props("flat dense round color=primary").tooltip(
                    t("personal_loans.action_repayment")
                )
            ui.button(
                icon="delete",
                on_click=lambda _e, lid=loan.id: on_delete(lid),
            ).props("flat dense round color=negative").tooltip(t("personal_loans.action_delete"))

        if loan.repayments:
            repayment_cls = amount_css_class("expense" if is_outgoing else "income")
            with ui.column().classes("w-full mt-2 gap-0 pl-8"):
                ui.label(t("personal_loans.repayments_heading")).classes(
                    "text-xs uppercase tracking-wide text-slate-500"
                )
                for r in loan.repayments:
                    with ui.row().classes("w-full items-center gap-3 py-1"):
                        ui.label(fmt_date(r.date)).classes("w-24 text-xs text-slate-500")
                        if r.note:
                            ui.label(r.note).classes("flex-1 text-sm")
                        else:
                            ui.label("").classes("flex-1")
                        if r.linked_transaction_id is not None:
                            ui.badge(
                                t(
                                    "personal_loans.repayment_linked",
                                    id=r.linked_transaction_id,
                                )
                            ).props("color=grey-6 outline rounded")
                        ui.label(f"-{fmt_amount(r.amount)} {loan.currency}").classes(
                            f"{repayment_cls} w-28 text-right text-sm"
                        )
                        ui.button(
                            icon="close",
                            on_click=lambda _e, rid=r.id: on_rep_delete(rid),
                        ).props("flat dense round color=grey-7").tooltip(
                            t("personal_loans.repayment_delete")
                        )


def _loan_row_subtitle(loan: Any) -> None:
    parts: list[str] = []
    parts.append(t("personal_loans.row_opened", date=fmt_date(loan.opened_at)))
    if loan.status == LoanStatus.SETTLED and loan.settled_at:
        parts.append(
            t(
                "personal_loans.row_settled",
                date=fmt_date(loan.settled_at.date()),
            )
        )
    elif loan.due_at:
        parts.append(t("personal_loans.row_due", date=fmt_date(loan.due_at)))
    if loan.notes:
        parts.append(notes_preview(loan.notes))
    ui.label(" · ".join(parts)).classes("text-xs text-slate-500")
