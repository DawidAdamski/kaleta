# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings → Security: the data passphrase card (``hosted-field-encryption``).

Change the passphrase, see whether a recovery code exists, replace the code,
and lock this browser now. Shown only while encryption is on.
"""

from __future__ import annotations

from nicegui import ui

from kaleta.auth.unlock import UNLOCK_PATH, lock_this_session, with_key_service
from kaleta.exceptions import KaletaError, ValidationError
from kaleta.i18n import t
from kaleta.services.key_service import KeyService
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.unlock import passphrase_problem, recovery_code_panel


async def render_data_passphrase_card() -> None:
    async def _has_recovery(service: KeyService) -> bool:
        return await service.has_recovery()

    has_recovery = await with_key_service(_has_recovery)

    with ui.card().classes("p-6 w-full mb-6"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("key", color="primary").classes("text-xl")
            ui.label(t("settings.passphrase_title")).classes("text-lg font-semibold")
        ui.label(t("settings.passphrase_hint")).classes("text-xs text-slate-500 mb-4")
        with ui.row().classes("items-center gap-3 mb-4"):
            ui.icon(
                "verified_user" if has_recovery else "gpp_maybe",
                color="positive" if has_recovery else "warning",
            )
            ui.label(
                t(
                    "settings.passphrase_recovery_set"
                    if has_recovery
                    else "settings.passphrase_recovery_missing"
                )
            ).classes("text-sm")
        with ui.row().classes("gap-2 flex-wrap"):
            ui.button(
                t("settings.passphrase_change"), icon="password", on_click=_open_change
            ).props("outline")
            ui.button(
                t("settings.passphrase_new_recovery"), icon="restart_alt", on_click=_open_regenerate
            ).props("outline")
            ui.button(t("settings.passphrase_lock_now"), icon="lock", on_click=_lock_now).props(
                "flat color=negative"
            )


def _lock_now() -> None:
    lock_this_session()
    ui.navigate.to(f"{UNLOCK_PATH}?redirect_to=/settings")


async def _open_change() -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-sm gap-3"):
        ui.label(t("settings.passphrase_change")).classes("text-lg font-semibold")
        current = ui.input(t("settings.passphrase_current"), password=True).classes("w-full")
        new = ui.input(t("unlock.new_passphrase"), password=True).classes("w-full")
        confirm = ui.input(t("unlock.confirm_passphrase"), password=True).classes("w-full")
        error = ui.label("").classes("text-sm text-negative")

        async def _save() -> None:
            problem = passphrase_problem(new.value or "", confirm.value or "")
            if problem is not None:
                error.set_text(problem)
                return
            old_value, new_value = current.value or "", new.value or ""

            async def _change(service: KeyService) -> None:
                await service.change_passphrase(old_value, new_value)

            try:
                await with_key_service(_change)
            except ValidationError:
                error.set_text(t("settings.passphrase_current_wrong"))
                return
            except KaletaError as exc:
                notify_kaleta_error(exc)
                return
            dialog.submit(True)

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(t("common.save"), on_click=_save).props("color=primary")
    changed = await dialog
    dialog.delete()
    if changed:
        ui.notify(t("settings.passphrase_changed"), type="positive")


async def _open_regenerate() -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3") as card:
        ui.label(t("settings.passphrase_new_recovery")).classes("text-lg font-semibold")
        ui.label(t("settings.passphrase_new_recovery_hint")).classes("text-sm text-slate-500")
        passphrase = ui.input(t("unlock.passphrase"), password=True).classes("w-full")
        error = ui.label("").classes("text-sm text-negative")

        async def _go() -> None:
            value = passphrase.value or ""

            async def _regenerate(service: KeyService) -> str:
                return await service.regenerate_recovery_code(value)

            try:
                code = await with_key_service(_regenerate)
            except ValidationError:
                error.set_text(t("unlock.wrong_passphrase"))
                return
            except KaletaError as exc:
                notify_kaleta_error(exc)
                return
            card.clear()
            with card:
                recovery_code_panel(
                    code, on_done=lambda: dialog.submit(True), done_key="common.close"
                )

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(t("settings.passphrase_new_recovery"), on_click=_go).props("color=primary")
    await dialog
    dialog.delete()
