# SPDX-License-Identifier: AGPL-3.0-or-later
"""First-run account creation when the database has no user row."""

from __future__ import annotations

from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.session import is_authenticated, login_session
from kaleta.i18n import t
from kaleta.services import AuthService, with_session
from kaleta.views.auth_common import AUTH_CONTROL, auth_page_shell
from kaleta.views.theme import ERROR_SLOT


def register() -> None:
    @ui.page("/create-account")
    async def create_account_page() -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse("/")

        async def _guard(session: Any) -> bool:
            return await AuthService(session).auth_state() == "no_user"

        if not await with_session(_guard):
            return RedirectResponse("/login")

        shell = await auth_page_shell("auth.create_title", "auth.create_subtitle")

        with shell, ui.column().classes("w-full gap-3"):
            username = (
                ui.input(t("auth.username"))
                .props("autofocus outlined")
                .classes(f"w-full {AUTH_CONTROL}")
            )
            password = (
                ui.input(t("auth.password"), password=True, password_toggle_button=True)
                .props("outlined")
                .classes(f"w-full {AUTH_CONTROL}")
            )
            confirm = (
                ui.input(
                    t("auth.password_confirm"),
                    password=True,
                    password_toggle_button=True,
                )
                .props("outlined")
                .classes(f"w-full {AUTH_CONTROL}")
            )
            # The same reserved line the login page uses: a message that
            # appears must not move the button out from under the pointer.
            error = ui.label("").classes(f"{ERROR_SLOT} text-sm k-trend--neg")

            async def _submit() -> None:
                error.set_text("")
                name = (username.value or "").strip()
                pwd = password.value or ""
                pwd2 = confirm.value or ""

                if not name:
                    error.set_text(t("auth.username_required"))
                    return
                if len(pwd) < 8:
                    error.set_text(t("auth.password_too_short"))
                    return
                if pwd != pwd2:
                    error.set_text(t("auth.password_mismatch"))
                    return

                async def _create(session: Any) -> tuple[bool, str, int | None]:
                    auth = AuthService(session)
                    if await auth.auth_state() != "no_user":
                        return False, t("auth.create_not_allowed"), None
                    user = await auth.create_user(name, pwd)
                    await auth.record_login(username=user.username, success=True)
                    return True, user.username, user.id

                ok, message, user_id = await with_session(_create)
                if not ok or user_id is None:
                    error.set_text(message)
                    return

                login_session(user_id=user_id, username=message)
                ui.navigate.to("/wizard")

            confirm.on("keydown.enter", _submit)
            ui.button(
                t("auth.create_button"),
                icon="person_add",
                on_click=_submit,
            ).props("color=primary unelevated").classes(f"w-full {AUTH_CONTROL}")

        return None
