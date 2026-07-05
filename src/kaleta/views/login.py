# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login page — username + password against the single app user."""

from __future__ import annotations

from typing import Any

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.session import is_authenticated, login_session
from kaleta.i18n import t
from kaleta.services import AuthService, with_session
from kaleta.views.auth_common import auth_page_shell


def _safe_redirect(path: str) -> str:
    if path.startswith("/") and not path.startswith("//"):
        return path
    return "/"


def register() -> None:
    @ui.page("/login")
    async def login_page(redirect_to: str = "/") -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse(_safe_redirect(redirect_to))

        async def _bootstrap(session: Any) -> str | None:
            state = await AuthService(session).auth_state()
            if state == "no_user":
                return "/create-account"
            if state == "placeholder":
                return "/secure-app"
            return None

        bootstrap = await with_session(_bootstrap)
        if bootstrap is not None:
            return RedirectResponse(bootstrap)

        target = _safe_redirect(redirect_to)
        shell = auth_page_shell("auth.login_title", "auth.login_subtitle")

        with shell, ui.card().classes("w-full max-w-md p-6"), ui.column().classes("w-full gap-4"):
            username = ui.input(t("auth.username")).props("autofocus").classes("w-full")
            password = (
                ui.input(t("auth.password"), password=True, password_toggle_button=True)
                .classes("w-full")
                .on("keydown.enter", lambda: None)
            )
            error = ui.label("").classes("text-sm text-negative")
            error.set_visibility(False)

            async def _submit() -> None:
                error.set_visibility(False)
                name = (username.value or "").strip()
                pwd = password.value or ""

                async def _try(session: Any) -> tuple[bool, int | None]:
                    auth = AuthService(session)
                    user = await auth.authenticate(name, pwd)
                    if user is None:
                        await auth.record_login(username=name or None, success=False)
                        return False, None
                    await auth.record_login(username=user.username, success=True)
                    return True, user.id

                ok, user_id = await with_session(_try)
                if not ok or user_id is None:
                    error.set_text(t("auth.login_failed"))
                    error.set_visibility(True)
                    return

                login_session(user_id=user_id, username=name)
                ui.navigate.to(target)

            password.on("keydown.enter", _submit)
            ui.button(
                t("auth.login_button"),
                icon="login",
                on_click=_submit,
            ).props("color=primary unelevated").classes("w-full")

        return None
