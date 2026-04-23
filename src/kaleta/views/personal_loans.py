from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import CategoryType
from kaleta.models.personal_loan import LoanDirection, LoanStatus
from kaleta.schemas.personal_loan import (
    PersonalLoanCreate,
    PersonalLoanUpdate,
    RepaymentCreate,
)
from kaleta.services import (
    AccountService,
    CategoryService,
    PersonalLoanService,
)
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def _fmt_date(d: datetime.date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _compute_remaining(principal: Decimal, repayments: list[Decimal]) -> Decimal:
    return (principal - sum(repayments, Decimal("0"))).quantize(Decimal("0.01"))


def register() -> None:
    @ui.page("/wizard/personal-loans")
    async def personal_loans_page() -> None:
        async with AsyncSessionFactory() as session:
            svc = PersonalLoanService(session)
            loans = await svc.list_loans()
            counterparties = await svc.list_counterparties()
            totals = await svc.totals()
            accounts = await AccountService(session).list()
            expense_cats = await CategoryService(session).list(
                type=CategoryType.EXPENSE
            )
            income_cats = await CategoryService(session).list(
                type=CategoryType.INCOME
            )

        counterparty_opts: dict[int, str] = {c.id: c.name for c in counterparties}
        account_opts: dict[int, str] = {a.id: a.name for a in accounts}
        expense_cat_opts: dict[int, str] = {c.id: c.name for c in expense_cats}
        income_cat_opts: dict[int, str] = {c.id: c.name for c in income_cats}

        with page_layout(t("personal_loans.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("personal_loans.title")).classes(PAGE_TITLE)
                    ui.label(t("personal_loans.subtitle")).classes(BODY_MUTED)
                with ui.row().classes("items-center gap-4"):
                    with ui.column().classes("items-end gap-0"):
                        ui.label(t("personal_loans.they_owe_you")).classes(
                            "text-xs text-slate-500 uppercase tracking-wide"
                        )
                        ui.label(_fmt(totals.they_owe_you)).classes(
                            f"{AMOUNT_INCOME} text-lg font-bold"
                        )
                    with ui.column().classes("items-end gap-0"):
                        ui.label(t("personal_loans.you_owe")).classes(
                            "text-xs text-slate-500 uppercase tracking-wide"
                        )
                        ui.label(_fmt(totals.you_owe)).classes(
                            f"{AMOUNT_EXPENSE} text-lg font-bold"
                        )

            # ── Add/Edit loan dialog ──────────────────────────────────────
            editing_state: dict[str, int | None] = {"id": None}

            with ui.dialog() as loan_dialog, ui.card().classes("w-[520px] gap-3"):
                loan_dialog_title = ui.label(
                    t("personal_loans.dialog_title_new")
                ).classes("text-lg font-bold")

                counterparty_in = (
                    ui.input(label=t("personal_loans.field_counterparty"))
                    .props("dense outlined")
                    .classes("w-full")
                )
                ui.label(t("personal_loans.field_counterparty_hint")).classes(
                    BODY_MUTED
                )

                direction_in = (
                    ui.select(
                        options={
                            LoanDirection.OUTGOING.value: t(
                                "personal_loans.direction_outgoing"
                            ),
                            LoanDirection.INCOMING.value: t(
                                "personal_loans.direction_incoming"
                            ),
                        },
                        label=t("personal_loans.field_direction"),
                        value=LoanDirection.OUTGOING.value,
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )

                with ui.row().classes("w-full gap-2"):
                    principal_in = (
                        ui.number(
                            label=t("personal_loans.field_principal"),
                            value=0,
                            min=0,
                            format="%.2f",
                        )
                        .props("dense outlined")
                        .classes("flex-1")
                    )
                    currency_in = (
                        ui.input(
                            label=t("personal_loans.field_currency"),
                            value="PLN",
                        )
                        .props("dense outlined maxlength=3")
                        .classes("w-24")
                    )

                with ui.row().classes("w-full gap-2"):
                    opened_in = (
                        ui.input(label=t("personal_loans.field_opened_at"))
                        .props("dense outlined type=date")
                        .classes("flex-1")
                    )
                    due_in = (
                        ui.input(label=t("personal_loans.field_due_at"))
                        .props("dense outlined type=date")
                        .classes("flex-1")
                    )

                notes_in = (
                    ui.textarea(label=t("personal_loans.field_notes"))
                    .props("dense outlined rows=2 autogrow")
                    .classes("w-full")
                )

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=loan_dialog.close).props(
                        "flat"
                    )
                    loan_save_btn = ui.button(
                        t("common.save"), icon="check"
                    ).props("color=primary unelevated")

            # ── Repayment dialog ──────────────────────────────────────────
            repayment_state: dict[str, int | None] = {"loan_id": None}

            with ui.dialog() as rep_dialog, ui.card().classes("w-[520px] gap-3"):
                ui.label(t("personal_loans.repayment_dialog_title")).classes(
                    "text-lg font-bold"
                )
                with ui.row().classes("w-full gap-2"):
                    rep_amount = (
                        ui.number(
                            label=t("personal_loans.repayment_field_amount"),
                            value=0,
                            min=0,
                            format="%.2f",
                        )
                        .props("dense outlined")
                        .classes("flex-1")
                    )
                    rep_date = (
                        ui.input(label=t("personal_loans.repayment_field_date"))
                        .props("dense outlined type=date")
                        .classes("flex-1")
                    )
                rep_note = (
                    ui.textarea(label=t("personal_loans.repayment_field_note"))
                    .props("dense outlined rows=2 autogrow")
                    .classes("w-full")
                )
                # The "Mirror as transaction" block — account + optional category.
                link_options: dict[int, str] = {0: t("personal_loans.repayment_field_link_none")}
                link_options.update(account_opts)
                rep_link_account = (
                    ui.select(
                        options=link_options,
                        label=t("personal_loans.repayment_field_link_account"),
                        value=0,
                    )
                    .props("dense outlined")
                    .classes("w-full")
                )
                ui.label(t("personal_loans.repayment_field_link_hint")).classes(
                    BODY_MUTED
                )
                rep_link_category = (
                    ui.select(
                        options={**expense_cat_opts, **income_cat_opts},
                        label=t("personal_loans.repayment_field_link_category"),
                        with_input=True,
                    )
                    .props("dense outlined clearable")
                    .classes("w-full")
                )
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=rep_dialog.close).props(
                        "flat"
                    )
                    rep_save_btn = ui.button(
                        t("common.save"), icon="check"
                    ).props("color=primary unelevated")

            # ── Delete-confirm dialog ─────────────────────────────────────
            pending_delete: dict[str, int] = {"id": 0}

            with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
                ui.label(t("personal_loans.confirm_delete_title")).classes(
                    "text-lg font-bold"
                )
                ui.label(t("personal_loans.confirm_delete_body")).classes(BODY_MUTED)
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=delete_dialog.close).props(
                        "flat"
                    )
                    confirm_delete_btn = ui.button(
                        t("personal_loans.confirm_delete_confirm"), icon="delete"
                    ).props("color=negative unelevated")

            # ── Handlers ─────────────────────────────────────────────────
            def _open_add_loan() -> None:
                editing_state["id"] = None
                loan_dialog_title.set_text(t("personal_loans.dialog_title_new"))
                counterparty_in.set_value("")
                direction_in.set_value(LoanDirection.OUTGOING.value)
                principal_in.set_value(0)
                currency_in.set_value("PLN")
                opened_in.set_value(datetime.date.today().isoformat())
                due_in.set_value("")
                notes_in.set_value("")
                loan_dialog.open()

            def _open_edit_loan(loan: Any) -> None:
                editing_state["id"] = loan.id
                loan_dialog_title.set_text(t("personal_loans.dialog_title_edit"))
                cp_name = counterparty_opts.get(loan.counterparty_id, "")
                counterparty_in.set_value(cp_name)
                direction_in.set_value(loan.direction.value)
                principal_in.set_value(float(loan.principal))
                currency_in.set_value(loan.currency)
                opened_in.set_value(loan.opened_at.isoformat())
                due_in.set_value(loan.due_at.isoformat() if loan.due_at else "")
                notes_in.set_value(loan.notes or "")
                loan_dialog.open()

            async def _save_loan() -> None:
                try:
                    cp_name = (counterparty_in.value or "").strip()
                    if not cp_name:
                        ui.notify("Counterparty required", type="warning")
                        return
                    principal = Decimal(str(principal_in.value or 0))
                    if principal <= 0:
                        ui.notify("Amount must be > 0", type="warning")
                        return
                    opened_at = datetime.date.fromisoformat(
                        opened_in.value or datetime.date.today().isoformat()
                    )
                    due_at = (
                        datetime.date.fromisoformat(due_in.value)
                        if due_in.value
                        else None
                    )
                    currency = (currency_in.value or "PLN").strip().upper()[:3] or "PLN"
                    direction = LoanDirection(direction_in.value)
                    notes = (notes_in.value or "").strip() or None
                except (ValueError, TypeError) as exc:
                    ui.notify(str(exc), type="negative")
                    return

                async with AsyncSessionFactory() as s:
                    loan_svc = PersonalLoanService(s)
                    cp = await loan_svc.upsert_counterparty(cp_name)
                    if editing_state["id"] is None:
                        await loan_svc.create_loan(
                            PersonalLoanCreate(
                                counterparty_id=cp.id,
                                direction=direction,
                                principal=principal,
                                currency=currency,
                                opened_at=opened_at,
                                due_at=due_at,
                                notes=notes,
                            )
                        )
                    else:
                        await loan_svc.update_loan(
                            editing_state["id"],
                            PersonalLoanUpdate(
                                counterparty_id=cp.id,
                                direction=direction,
                                principal=principal,
                                currency=currency,
                                opened_at=opened_at,
                                due_at=due_at,
                                notes=notes,
                            ),
                        )
                loan_dialog.close()
                ui.notify(t("personal_loans.saved"), type="positive")
                ui.navigate.reload()

            loan_save_btn.on_click(_save_loan)

            def _open_delete_dialog(loan_id: int) -> None:
                pending_delete["id"] = loan_id
                delete_dialog.open()

            async def _confirm_delete() -> None:
                async with AsyncSessionFactory() as s:
                    await PersonalLoanService(s).delete_loan(pending_delete["id"])
                delete_dialog.close()
                ui.notify(t("personal_loans.deleted"), type="positive")
                ui.navigate.reload()

            confirm_delete_btn.on_click(_confirm_delete)

            def _open_repayment_dialog(loan_id: int) -> None:
                repayment_state["loan_id"] = loan_id
                rep_amount.set_value(0)
                rep_date.set_value(datetime.date.today().isoformat())
                rep_note.set_value("")
                rep_link_account.set_value(0)
                rep_link_category.set_value(None)
                rep_dialog.open()

            async def _save_repayment() -> None:
                loan_id = repayment_state["loan_id"]
                if loan_id is None:
                    return
                try:
                    amount = Decimal(str(rep_amount.value or 0))
                    if amount <= 0:
                        ui.notify("Amount must be > 0", type="warning")
                        return
                    rep_date_value = datetime.date.fromisoformat(
                        rep_date.value or datetime.date.today().isoformat()
                    )
                    link_acc_raw = rep_link_account.value
                    link_acc = (
                        int(link_acc_raw)
                        if link_acc_raw is not None and int(link_acc_raw) != 0
                        else None
                    )
                    link_cat = (
                        int(rep_link_category.value)
                        if rep_link_category.value is not None
                        else None
                    )
                    note = (rep_note.value or "").strip() or None
                except (ValueError, TypeError) as exc:
                    ui.notify(str(exc), type="negative")
                    return

                async with AsyncSessionFactory() as s:
                    await PersonalLoanService(s).record_repayment(
                        loan_id,
                        RepaymentCreate(
                            amount=amount,
                            date=rep_date_value,
                            note=note,
                            link_account_id=link_acc,
                            link_category_id=link_cat,
                        ),
                    )
                rep_dialog.close()
                ui.notify(t("personal_loans.repayment_recorded"), type="positive")
                ui.navigate.reload()

            rep_save_btn.on_click(_save_repayment)

            async def _delete_repayment(rep_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await PersonalLoanService(s).delete_repayment(rep_id)
                ui.notify(t("personal_loans.repayment_deleted"), type="positive")
                ui.navigate.reload()

            # ── Top-right Add button ─────────────────────────────────────
            with ui.row().classes("w-full justify-end"):
                ui.button(
                    t("personal_loans.add"), icon="add", on_click=_open_add_loan
                ).props("color=primary unelevated size=sm")

            # ── List rendering ───────────────────────────────────────────
            outstanding = [ln for ln in loans if ln.status == LoanStatus.OUTSTANDING]
            settled = [ln for ln in loans if ln.status == LoanStatus.SETTLED]

            if not loans:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("personal_loans.empty")).classes(f"{BODY_MUTED} py-2")

            if outstanding:
                with ui.card().classes(SECTION_CARD):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(t("personal_loans.section_outstanding")).classes(
                            SECTION_HEADING
                        )
                        ui.badge(
                            t(
                                "personal_loans.outstanding_count",
                                count=totals.outstanding_count,
                            )
                        ).props("color=amber-7 rounded")
                    for loan in outstanding:
                        _render_loan_row(
                            loan,
                            on_edit=_open_edit_loan,
                            on_delete=_open_delete_dialog,
                            on_repayment=_open_repayment_dialog,
                            on_rep_delete=_delete_repayment,
                        )

            if settled:
                with ui.card().classes(SECTION_CARD):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(t("personal_loans.section_settled")).classes(
                            SECTION_HEADING
                        )
                        ui.badge(
                            t(
                                "personal_loans.settled_count",
                                count=totals.settled_count,
                            )
                        ).props("color=positive rounded")
                    for loan in settled:
                        _render_loan_row(
                            loan,
                            on_edit=_open_edit_loan,
                            on_delete=_open_delete_dialog,
                            on_repayment=_open_repayment_dialog,
                            on_rep_delete=_delete_repayment,
                        )


def _render_loan_row(
    loan: Any,
    *,
    on_edit: Any,
    on_delete: Any,
    on_repayment: Any,
    on_rep_delete: Any,
) -> None:
    repaid_amounts = [r.amount for r in loan.repayments]
    remaining = _compute_remaining(loan.principal, repaid_amounts)
    is_outgoing = loan.direction == LoanDirection.OUTGOING
    amount_cls = AMOUNT_INCOME if is_outgoing else AMOUNT_EXPENSE
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
                            amount=_fmt(loan.principal),
                            currency=loan.currency,
                        )
                    ).classes(f"{BODY_MUTED} text-sm")
                else:
                    ui.label(
                        t(
                            "personal_loans.row_remaining",
                            amount=_fmt(remaining),
                            currency=loan.currency,
                        )
                    ).classes(f"{amount_cls} text-base font-bold")
                    ui.label(
                        t(
                            "personal_loans.row_principal",
                            amount=_fmt(loan.principal),
                            currency=loan.currency,
                        )
                    ).classes("text-xs text-slate-500")
            ui.button(
                icon="edit", on_click=lambda _e, ll=loan: on_edit(ll)
            ).props("flat dense round color=grey-7").tooltip(
                t("personal_loans.action_edit")
            )
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
            ).props("flat dense round color=negative").tooltip(
                t("personal_loans.action_delete")
            )

        # Repayments list (always visible so the user sees the audit trail).
        if loan.repayments:
            with ui.column().classes("w-full mt-2 gap-0 pl-8"):
                ui.label(t("personal_loans.repayments_heading")).classes(
                    "text-xs uppercase tracking-wide text-slate-500"
                )
                for r in loan.repayments:
                    with ui.row().classes("w-full items-center gap-3 py-1"):
                        ui.label(_fmt_date(r.date)).classes(
                            "w-24 text-xs text-slate-500"
                        )
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
                        ui.label(
                            f"-{_fmt(r.amount)} {loan.currency}"
                        ).classes(
                            f"{AMOUNT_EXPENSE if is_outgoing else AMOUNT_INCOME} "
                            "w-28 text-right text-sm"
                        )
                        ui.button(
                            icon="close",
                            on_click=lambda _e, rid=r.id: on_rep_delete(rid),
                        ).props("flat dense round color=grey-7").tooltip(
                            t("personal_loans.repayment_delete")
                        )


def _loan_row_subtitle(loan: Any) -> None:
    parts: list[str] = []
    parts.append(t("personal_loans.row_opened", date=_fmt_date(loan.opened_at)))
    if loan.status == LoanStatus.SETTLED and loan.settled_at:
        parts.append(
            t(
                "personal_loans.row_settled",
                date=_fmt_date(loan.settled_at.date()),
            )
        )
    elif loan.due_at:
        parts.append(t("personal_loans.row_due", date=_fmt_date(loan.due_at)))
    if loan.notes:
        parts.append(loan.notes[:80] + ("…" if len(loan.notes) > 80 else ""))
    ui.label(" · ".join(parts)).classes("text-xs text-slate-500")
