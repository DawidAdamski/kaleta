# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data passphrase: choose it once, type it after every sign-in.

``hosted-field-encryption``. With encryption on, a signed-in session holds no
key until this page has opened it; the route guard sends every other page
here. Three faces, by the member's key status:

- **set up** — no key block yet: the hosted sign-up's second step (at the first
  sign-in after the e-mail is confirmed) and a self-hosted install's first
  sign-in. Ends on the recovery code, shown once, which must be acknowledged;
- **waiting** — an invited member whose data key has not been shared yet;
- **unlock** — the passphrase, or (behind a link) the recovery code and a new
  passphrase.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.redirects import safe_redirect
from kaleta.auth.session import finish_logout, is_authenticated, is_unlocked
from kaleta.auth.unlock import (
    current_session_key,
    is_login_password,
    with_key_service,
)
from kaleta.config import settings
from kaleta.exceptions import ConflictError, KaletaError, ValidationError
from kaleta.i18n import t
from kaleta.services.key_service import PASSPHRASE_MIN_LENGTH, KeyService, KeyStatus
from kaleta.views.auth_common import (
    auth_action,
    auth_error_slot,
    auth_field,
    auth_page_shell,
    auth_submit,
)
from kaleta.views.theme import AUTH_SUBTITLE

RECOVERY_FILENAME = "kaleta-recovery-code.txt"


def passphrase_problem(passphrase: str, confirm: str) -> str | None:
    """What is wrong with a new passphrase and its confirmation, in the page's words."""
    if len(passphrase) < PASSPHRASE_MIN_LENGTH:
        return t("unlock.passphrase_too_short", count=PASSPHRASE_MIN_LENGTH)
    if passphrase != confirm:
        return t("unlock.passphrase_mismatch")
    return None


def recovery_code_panel(code: str, *, on_done: Callable[[], Any], done_key: str) -> None:
    """The recovery code, shown once: copy, download, and an "I saved it" gate.

    The button that leaves stays disabled until the box is ticked — the plan's
    forced acknowledgement — because this is the only time the code exists
    anywhere but on the user's own paper.
    """
    with ui.column().classes("w-full gap-3"):
        ui.label(t("unlock.recovery_title")).classes("text-lg font-semibold")
        ui.label(t("unlock.recovery_hint")).classes(AUTH_SUBTITLE)
        ui.label(code).classes(
            "font-mono text-base select-all p-3 rounded border border-slate-300 w-full"
        ).props('data-testid="recovery-code"')
        with ui.row().classes("gap-2"):
            ui.button(
                t("unlock.recovery_copy"),
                icon="content_copy",
                on_click=lambda: ui.clipboard.write(code),
            ).props("outline no-caps")
            ui.button(
                t("unlock.recovery_download"),
                icon="download",
                on_click=lambda: ui.download(
                    (t("unlock.recovery_file", code=code) + "\n").encode("utf-8"),
                    filename=RECOVERY_FILENAME,
                ),
            ).props("outline no-caps")
        saved = ui.checkbox(t("unlock.recovery_saved"))
        done = auth_submit(done_key, on_done)
        done.bind_enabled_from(saved, "value")


def register() -> None:
    @ui.page("/unlock")
    async def unlock_page(redirect_to: str = "/") -> RedirectResponse | None:
        target = safe_redirect(redirect_to)
        if not is_authenticated():
            return RedirectResponse("/login")
        if not settings.encryption_enabled or is_unlocked():
            return RedirectResponse(target)

        async def _status(service: KeyService) -> KeyStatus:
            return await service.status()

        status = await with_key_service(_status)
        if status == "setup_required":
            shell = await auth_page_shell("unlock.setup_title", "unlock.setup_subtitle")
            with shell:
                _setup_form(target)
        elif status == "awaiting_key":
            shell = await auth_page_shell("unlock.waiting_title", "unlock.waiting_subtitle")
            with shell:
                auth_action("unlock.sign_out", finish_logout)
        else:
            shell = await auth_page_shell("unlock.title", "unlock.subtitle")
            with shell:
                _unlock_form(target)
        return None


def _setup_form(target: str) -> None:
    with ui.column().classes("w-full gap-4") as form:
        passphrase = auth_field(
            "unlock.new_passphrase", password=True, password_toggle_button=True
        ).props("autofocus")
        confirm = auth_field("unlock.confirm_passphrase", password=True)
        ui.label(t("unlock.setup_warning")).classes(f"{AUTH_SUBTITLE} text-xs")
        say = auth_error_slot()

        async def _submit() -> None:
            say("")
            value = passphrase.value or ""
            problem = passphrase_problem(value, confirm.value or "")
            if problem is None and settings.tenancy != "multi" and await is_login_password(value):
                problem = t("unlock.passphrase_is_password")
            if problem is not None:
                say(problem)
                return
            button.disable()
            session_key = current_session_key()

            async def _setup(service: KeyService) -> str:
                return (await service.setup(session_key, value)).recovery_code

            try:
                code = await with_key_service(_setup)
            except KaletaError as exc:
                button.enable()
                say(exc.message)
                return
            form.clear()
            with form:
                recovery_code_panel(
                    code,
                    on_done=lambda: ui.navigate.to(target),
                    done_key="unlock.continue",
                )

        confirm.on("keydown.enter", _submit)
        button = auth_submit("unlock.setup_button", _submit)


def _unlock_form(target: str) -> None:
    with ui.column().classes("w-full gap-4") as form:
        with ui.column().classes("w-full gap-0") as passphrase_block:
            passphrase = auth_field(
                "unlock.passphrase", password=True, password_toggle_button=True
            ).props("autofocus")
        with ui.column().classes("w-full gap-4") as recovery_block:
            code = auth_field("unlock.recovery_code")
            new_passphrase = auth_field("unlock.new_passphrase", password=True)
            confirm = auth_field("unlock.confirm_passphrase", password=True)
        recovery_block.set_visibility(False)
        say = auth_error_slot()

        async def _unlock() -> None:
            session_key = current_session_key()
            value = passphrase.value or ""

            async def _open(service: KeyService) -> None:
                await service.unlock(session_key, value)

            try:
                await with_key_service(_open)
            except ValidationError:
                say(t("unlock.wrong_passphrase"))
                passphrase.set_value("")
                return
            except ConflictError:
                say(t("unlock.waiting_subtitle"))
                return
            ui.navigate.to(target)

        async def _recover() -> None:
            problem = passphrase_problem(new_passphrase.value or "", confirm.value or "")
            if problem is not None:
                say(problem)
                return
            session_key = current_session_key()
            typed, fresh_passphrase = code.value or "", new_passphrase.value or ""

            async def _run(service: KeyService) -> str:
                return await service.recover(session_key, typed, fresh_passphrase)

            try:
                fresh = await with_key_service(_run)
            except ValidationError:
                say(t("unlock.wrong_recovery_code"))
                return
            form.clear()
            with form:
                ui.label(t("unlock.recovered")).classes(AUTH_SUBTITLE)
                recovery_code_panel(
                    fresh, on_done=lambda: ui.navigate.to(target), done_key="unlock.continue"
                )

        async def _submit() -> None:
            say("")
            if recovery_block.visible:
                await _recover()
            else:
                await _unlock()

        def _toggle() -> None:
            say("")
            using_recovery = not recovery_block.visible
            recovery_block.set_visibility(using_recovery)
            passphrase_block.set_visibility(not using_recovery)
            switch.set_text(t("unlock.use_passphrase" if using_recovery else "unlock.use_recovery"))
            submit.set_text(t("unlock.recover_button" if using_recovery else "unlock.button"))

        passphrase.on("keydown.enter", _submit)
        confirm.on("keydown.enter", _submit)
        submit = auth_submit("unlock.button", _submit)
        switch = auth_action("unlock.use_recovery", _toggle)
        auth_action("unlock.sign_out", finish_logout)
