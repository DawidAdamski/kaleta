# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings → Data: "Delete my account" — the hosted owner's GDPR path.

Shown only on a hosted instance and only to the account's owner. Two steps:
the first lists every member who loses access, the second asks for the data
passphrase. A member who is not the owner leaves the household instead
(``hosted-household-sharing``).
"""

from __future__ import annotations

from nicegui import ui

from kaleta.auth.account_deletion import delete_signed_in_account, deletion_overview
from kaleta.auth.session import finish_logout
from kaleta.exceptions import KaletaError, ValidationError
from kaleta.i18n import t
from kaleta.services.account_deletion_service import AccountMember
from kaleta.views.error_handling import notify_kaleta_error


async def render_delete_account_section() -> None:
    overview = await deletion_overview()
    if not overview.allowed:
        return
    with ui.card().classes("p-6 w-full mt-4"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("person_remove", color="negative").classes("text-xl")
            ui.label(t("settings.delete_account_title")).classes("text-lg font-semibold")
        ui.label(t("settings.delete_account_hint")).classes("text-xs text-slate-500 mb-4")
        ui.button(
            t("settings.delete_account_btn"),
            icon="delete_forever",
            on_click=lambda: _open_dialog(overview.members),
        ).props("outline color=negative")


async def _open_dialog(members: list[AccountMember]) -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3") as card:
        _confirm_step(card, members, dialog)
    deleted = await dialog
    dialog.delete()
    if deleted:
        ui.notify(t("settings.delete_account_done"), type="positive")
        finish_logout()


def _confirm_step(card: ui.card, members: list[AccountMember], dialog: ui.dialog) -> None:
    ui.label(t("settings.delete_account_confirm_title")).classes("text-lg font-semibold")
    ui.label(t("settings.delete_account_confirm_body")).classes("text-sm text-negative")
    with ui.column().classes("gap-1 w-full").props('data-testid="delete-account-members"'):
        for member in members:
            role = (
                "settings.delete_account_role_owner"
                if member.is_owner
                else "settings.delete_account_role_member"
            )
            ui.label(f"{member.email} · {t(role)}").classes("text-sm")

    def _next() -> None:
        card.clear()
        with card:
            _passphrase_step(dialog)

    with ui.row().classes("gap-2 justify-end w-full"):
        ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
        ui.button(t("settings.delete_account_continue"), on_click=_next).props(
            "color=negative unelevated"
        )


def _passphrase_step(dialog: ui.dialog) -> None:
    ui.label(t("settings.delete_account_confirm_title")).classes("text-lg font-semibold")
    ui.label(t("settings.delete_account_passphrase_body")).classes("text-sm text-slate-600")
    passphrase = ui.input(t("unlock.passphrase"), password=True).classes("w-full")
    error = ui.label("").classes("text-sm text-negative")

    async def _delete() -> None:
        error.set_text("")
        try:
            await delete_signed_in_account(passphrase.value or "")
        except ValidationError:
            error.set_text(t("unlock.wrong_passphrase"))
            return
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return
        dialog.submit(True)

    with ui.row().classes("gap-2 justify-end w-full"):
        ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
        ui.button(
            t("settings.delete_account_final_btn"), icon="delete_forever", on_click=_delete
        ).props("color=negative unelevated")
