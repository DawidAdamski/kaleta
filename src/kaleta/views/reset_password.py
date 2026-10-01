# SPDX-License-Identifier: AGPL-3.0-or-later
"""Forgotten password on a hosted instance: ask for a link, then set a new one.

``/reset-password`` asks for the e-mail and has Supabase Auth send a link;
the link comes back here with ``?token_hash=…`` (the Supabase recovery e-mail
template must point at this page — see ``docs/deployment.md``) and the page
asks for the new password. A self-hosted install resets from the command line
(``kaleta --reset-password``), so there this page only sends you to log in.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import is_authenticated
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.views.auth_common import (
    auth_error_slot,
    auth_field,
    auth_link,
    auth_page_shell,
    auth_submit,
)
from kaleta.views.theme import AUTH_SUBTITLE


def register() -> None:
    @ui.page("/reset-password")
    async def reset_password_page(token_hash: str = "") -> RedirectResponse | None:
        provider = get_auth_provider()
        if provider.name != "supabase" or is_authenticated():
            return RedirectResponse("/login")

        if token_hash:
            shell = await auth_page_shell("auth.reset_new_title", "auth.reset_new_subtitle")
        else:
            shell = await auth_page_shell("auth.reset_title", "auth.reset_subtitle")

        with shell, ui.column().classes("w-full gap-4") as form:
            if not token_hash:
                email = auth_field("auth.email").props("autofocus")
                _say = auth_error_slot()

                async def _send() -> None:
                    _say("")
                    address = (email.value or "").strip()
                    if not address:
                        _say(t("auth.email_required"))
                        return
                    try:
                        await provider.request_password_reset(address)
                    except KaletaError as exc:
                        _say(exc.message)
                        return
                    form.clear()
                    with form:
                        ui.label(t("auth.reset_sent")).classes(AUTH_SUBTITLE)
                        auth_link("auth.have_account_link", "/login")

                email.on("keydown.enter", _send)
                auth_submit("auth.reset_send", _send)
                auth_link("auth.have_account_link", "/login")
                return None

            password = auth_field(
                "auth.password", password=True, password_toggle_button=True
            ).props("autofocus")
            confirm = auth_field(
                "auth.password_confirm", password=True, password_toggle_button=True
            )
            _say_new = auth_error_slot()

            async def _save() -> None:
                _say_new("")
                pwd = password.value or ""
                if len(pwd) < 8:
                    _say_new(t("auth.password_too_short"))
                    return
                if pwd != (confirm.value or ""):
                    _say_new(t("auth.password_mismatch"))
                    return
                try:
                    await provider.confirm_password_reset(token_hash, pwd)
                except KaletaError as exc:
                    _say_new(exc.message)
                    return
                ui.navigate.to("/login?reason=password_reset")

            confirm.on("keydown.enter", _save)
            auth_submit("auth.reset_new_button", _save)

        return None
