"""Personal loan add/edit, repayment, and delete dialogs."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.personal_loan import (
    LoanDirection,
    PersonalLoanCreate,
    PersonalLoanUpdate,
)
from kaleta.services import PersonalLoanService, with_session
from kaleta.services.personal_loan_service import (
    PersonalLoanFormError,
    parse_loan_form,
    parse_repayment_form,
)
from kaleta.views.theme import BODY_MUTED


def build_personal_loan_dialogs(
    *,
    counterparty_opts: dict[int, str],
    account_opts: dict[int, str],
    expense_cat_opts: dict[int, str],
    income_cat_opts: dict[int, str],
) -> tuple[
    Callable[[], None],
    Callable[[Any], None],
    Callable[[int], None],
    Callable[[int], None],
    Callable[[int], Awaitable[None]],
]:
    editing_state: dict[str, int | None] = {"id": None}
    repayment_state: dict[str, int | None] = {"loan_id": None}
    pending_delete: dict[str, int] = {"id": 0}

    with ui.dialog() as loan_dialog, ui.card().classes("w-[520px] gap-3"):
        loan_dialog_title = ui.label(t("personal_loans.dialog_title_new")).classes(
            "text-lg font-bold"
        )

        counterparty_in = (
            ui.input(label=t("personal_loans.field_counterparty"))
            .props("dense outlined")
            .classes("w-full")
        )
        ui.label(t("personal_loans.field_counterparty_hint")).classes(BODY_MUTED)

        direction_in = (
            ui.select(
                options={
                    LoanDirection.OUTGOING.value: t("personal_loans.direction_outgoing"),
                    LoanDirection.INCOMING.value: t("personal_loans.direction_incoming"),
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
            ui.button(t("common.cancel"), on_click=loan_dialog.close).props("flat")
            loan_save_btn = ui.button(t("common.save"), icon="check").props(
                "color=primary unelevated"
            )

    with ui.dialog() as rep_dialog, ui.card().classes("w-[520px] gap-3"):
        ui.label(t("personal_loans.repayment_dialog_title")).classes("text-lg font-bold")
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
        ui.label(t("personal_loans.repayment_field_link_hint")).classes(BODY_MUTED)
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
            ui.button(t("common.cancel"), on_click=rep_dialog.close).props("flat")
            rep_save_btn = ui.button(t("common.save"), icon="check").props(
                "color=primary unelevated"
            )

    with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
        ui.label(t("personal_loans.confirm_delete_title")).classes("text-lg font-bold")
        ui.label(t("personal_loans.confirm_delete_body")).classes(BODY_MUTED)
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
            confirm_delete_btn = ui.button(
                t("personal_loans.confirm_delete_confirm"), icon="delete"
            ).props("color=negative unelevated")

    def open_add_loan() -> None:
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

    def open_edit_loan(loan: Any) -> None:
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

    async def save_loan() -> None:
        try:
            (
                cp_name,
                direction,
                principal,
                currency,
                opened_at,
                due_at,
                notes,
            ) = parse_loan_form(
                counterparty=str(counterparty_in.value or ""),
                direction_value=str(direction_in.value or LoanDirection.OUTGOING.value),
                principal_value=principal_in.value,
                currency_value=str(currency_in.value or "PLN"),
                opened_value=str(opened_in.value or ""),
                due_value=str(due_in.value or ""),
                notes_value=str(notes_in.value or ""),
            )
        except PersonalLoanFormError as exc:
            ui.notify(exc.message, type="warning")
            return

        async def _persist(session: Any) -> None:
            loan_svc = PersonalLoanService(session)
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

        await with_session(_persist)
        loan_dialog.close()
        ui.notify(t("personal_loans.saved"), type="positive")
        ui.navigate.reload()

    loan_save_btn.on_click(save_loan)

    def open_delete_dialog(loan_id: int) -> None:
        pending_delete["id"] = loan_id
        delete_dialog.open()

    async def confirm_delete() -> None:
        async def _delete(session: Any) -> None:
            await PersonalLoanService(session).delete_loan(pending_delete["id"])

        await with_session(_delete)
        delete_dialog.close()
        ui.notify(t("personal_loans.deleted"), type="positive")
        ui.navigate.reload()

    confirm_delete_btn.on_click(confirm_delete)

    def open_repayment_dialog(loan_id: int) -> None:
        repayment_state["loan_id"] = loan_id
        rep_amount.set_value(0)
        rep_date.set_value(datetime.date.today().isoformat())
        rep_note.set_value("")
        rep_link_account.set_value(0)
        rep_link_category.set_value(None)
        rep_dialog.open()

    async def save_repayment() -> None:
        loan_id = repayment_state["loan_id"]
        if loan_id is None:
            return
        try:
            payload = parse_repayment_form(
                amount_value=rep_amount.value,
                date_value=str(rep_date.value or ""),
                link_account_value=rep_link_account.value,
                link_category_value=rep_link_category.value,
                note_value=str(rep_note.value or ""),
            )
        except PersonalLoanFormError as exc:
            ui.notify(exc.message, type="warning")
            return

        async def _record(session: Any) -> None:
            await PersonalLoanService(session).record_repayment(loan_id, payload)

        await with_session(_record)
        rep_dialog.close()
        ui.notify(t("personal_loans.repayment_recorded"), type="positive")
        ui.navigate.reload()

    rep_save_btn.on_click(save_repayment)

    async def delete_repayment(rep_id: int) -> None:
        async def _delete(session: Any) -> None:
            await PersonalLoanService(session).delete_repayment(rep_id)

        await with_session(_delete)
        ui.notify(t("personal_loans.repayment_deleted"), type="positive")
        ui.navigate.reload()

    return (
        open_add_loan,
        open_edit_loan,
        open_delete_dialog,
        open_repayment_dialog,
        delete_repayment,
    )
