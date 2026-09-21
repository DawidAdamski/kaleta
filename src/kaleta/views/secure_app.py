# SPDX-License-Identifier: AGPL-3.0-or-later
"""Upgrade the migration placeholder user to real credentials."""

from __future__ import annotations

from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.session import is_authenticated, login_session
from kaleta.exceptions import ValidationError
from kaleta.i18n import t
from kaleta.services import AuthService, with_session
from kaleta.views.auth_common import (
    auth_error_slot,
    auth_field,
    auth_page_shell,
    auth_submit,
)


def register() -> None:
    @ui.page("/secure-app")
    async def secure_app_page() -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse("/")

        async def _guard(session: Any) -> bool:
            return await AuthService(session).auth_state() == "placeholder"

        if not await with_session(_guard):
            return RedirectResponse("/login")

        shell = await auth_page_shell("auth.secure_title", "auth.secure_subtitle")

        with shell, ui.column().classes("w-full gap-4"):
            username = auth_field("auth.username").props("autofocus")
            password = auth_field("auth.password", password=True, password_toggle_button=True)
            confirm = auth_field(
                "auth.password_confirm", password=True, password_toggle_button=True
            )
            # The same reserved strip the login page uses: a message that
            # appears must not move the button out from under the pointer.
            _say = auth_error_slot()

            async def _submit() -> None:
                _say("")
                name = (username.value or "").strip()
                pwd = password.value or ""
                pwd2 = confirm.value or ""

                if not name:
                    _say(t("auth.username_required"))
                    return
                if len(pwd) < 8:
                    _say(t("auth.password_too_short"))
                    return
                if pwd != pwd2:
                    _say(t("auth.password_mismatch"))
                    return

                async def _secure(session: Any) -> tuple[bool, str, int | None]:
                    auth = AuthService(session)
                    try:
                        user = await auth.secure_placeholder(name, pwd)
                    except ValidationError as exc:
                        return False, exc.message, None
                    await auth.record_login(username=user.username, success=True)
                    return True, user.username, user.id

                ok, message, user_id = await with_session(_secure)
                if not ok or user_id is None:
                    _say(message)
                    return

                login_session(user_id=user_id, username=message)
                ui.navigate.to("/")

            confirm.on("keydown.enter", _submit)
            auth_submit("auth.secure_button", _submit)

        return None
