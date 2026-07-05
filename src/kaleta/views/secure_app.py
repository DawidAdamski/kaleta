"""Upgrade the migration placeholder user to real credentials."""

from __future__ import annotations

from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.session import is_authenticated, login_session
from kaleta.exceptions import ValidationError
from kaleta.i18n import t
from kaleta.services import AuthService, with_session
from kaleta.views.auth_common import auth_page_shell


def register() -> None:
    @ui.page("/secure-app")
    async def secure_app_page() -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse("/")

        async def _guard(session: Any) -> bool:
            return await AuthService(session).auth_state() == "placeholder"

        if not await with_session(_guard):
            return RedirectResponse("/login")

        shell = auth_page_shell("auth.secure_title", "auth.secure_subtitle")

        with shell, ui.card().classes("w-full max-w-md p-6"), ui.column().classes("w-full gap-4"):
            username = ui.input(t("auth.username")).props("autofocus").classes("w-full")
            password = ui.input(
                t("auth.password"), password=True, password_toggle_button=True
            ).classes("w-full")
            confirm = ui.input(
                t("auth.password_confirm"),
                password=True,
                password_toggle_button=True,
            ).classes("w-full")
            error = ui.label("").classes("text-sm text-negative")
            error.set_visibility(False)

            async def _submit() -> None:
                error.set_visibility(False)
                name = (username.value or "").strip()
                pwd = password.value or ""
                pwd2 = confirm.value or ""

                if not name:
                    error.set_text(t("auth.username_required"))
                    error.set_visibility(True)
                    return
                if len(pwd) < 8:
                    error.set_text(t("auth.password_too_short"))
                    error.set_visibility(True)
                    return
                if pwd != pwd2:
                    error.set_text(t("auth.password_mismatch"))
                    error.set_visibility(True)
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
                    error.set_text(message)
                    error.set_visibility(True)
                    return

                login_session(user_id=user_id, username=message)
                ui.navigate.to("/")

            confirm.on("keydown.enter", _submit)
            ui.button(
                t("auth.secure_button"),
                icon="lock",
                on_click=_submit,
            ).props("color=primary unelevated").classes("w-full")

        return None
