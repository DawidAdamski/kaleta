# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/change-password``: replace a password an administrator set.

An administrator who creates a family or resets a password sees the new
password — so its owner picks their own before anything else opens
(``instance-admin-panel``, KAL-ADM-009). The page guard sends every page here
while the session carries the flag; afterwards the member goes on to their
data passphrase, as after any sign-in.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.admin import CHANGE_PASSWORD_PATH, change_own_password, must_change_password
from kaleta.auth.session import finish_logout, is_authenticated
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.views.auth_common import (
    auth_action,
    auth_error_slot,
    auth_field,
    auth_page_shell,
    auth_submit,
)

#: ``LocalIdentityService.MIN_PASSWORD_LENGTH``; the service says so again.
_MIN_LENGTH = 8


def register() -> None:
    @ui.page(CHANGE_PASSWORD_PATH)
    async def change_password_page() -> RedirectResponse | None:
        if not is_authenticated():
            return RedirectResponse("/login")
        if not must_change_password():
            return RedirectResponse("/")

        shell = await auth_page_shell("auth.change_password_title", "auth.change_password_subtitle")
        with shell, ui.column().classes("w-full gap-4"):
            password = auth_field(
                "auth.new_password", password=True, password_toggle_button=True
            ).props("autofocus")
            confirm = auth_field(
                "auth.password_confirm", password=True, password_toggle_button=True
            )
            _say = auth_error_slot()

            async def _submit() -> None:
                _say("")
                pwd = password.value or ""
                if len(pwd) < _MIN_LENGTH:
                    _say(t("auth.password_too_short"))
                    return
                if pwd != (confirm.value or ""):
                    _say(t("auth.password_mismatch"))
                    return
                try:
                    await change_own_password(pwd)
                except KaletaError as exc:
                    _say(exc.message)
                    return
                ui.notify(t("auth.change_password_done"), type="positive")
                ui.navigate.to("/")

            confirm.on("keydown.enter", _submit)
            auth_submit("auth.change_password_button", _submit)
            auth_action("auth.logout", finish_logout)
        return None
