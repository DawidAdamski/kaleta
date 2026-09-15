# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login page — username + password against the single app user."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.login_rate_limit import login_rate_limiter
from kaleta.auth.session import is_authenticated, login_session
from kaleta.i18n import t
from kaleta.services import AuthService, with_session
from kaleta.views.auth_common import AUTH_CONTROL, auth_page_shell
from kaleta.views.theme import ERROR_SLOT


def _safe_redirect(path: str) -> str:
    if path.startswith("/") and not path.startswith("//"):
        return path
    return "/"


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def register() -> None:
    @ui.page("/login")
    async def login_page(
        request: Request,
        redirect_to: str = "/",
    ) -> RedirectResponse | None:
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
        rate_key = _client_key(request)
        shell = await auth_page_shell("auth.login_title", "auth.login_subtitle")

        # `AUTH_CONTROL` is `min-h-[48px]`, shared by all three auth pages: on
        # a phone this form is the whole screen, and a 40px field in the
        # middle of it is a target the thumb has to aim at.
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
                .on("keydown.enter", lambda: None)
            )
            # A reserved line, not a label that appears. Showing and hiding it
            # moved the button down under the pointer at the moment the user
            # was clicking it again — which is how a second attempt became a
            # misclick.
            error = ui.label("").classes(f"{ERROR_SLOT} text-sm k-trend--neg")

            async def _submit() -> None:
                error.set_text("")
                if login_rate_limiter.is_locked(rate_key):
                    secs = login_rate_limiter.remaining_lock_seconds(rate_key)
                    error.set_text(t("auth.login_rate_limited", seconds=secs))
                    return

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
                    locked = login_rate_limiter.record_failure(rate_key)
                    if locked:
                        secs = login_rate_limiter.remaining_lock_seconds(rate_key)
                        error.set_text(t("auth.login_rate_limited", seconds=secs))
                    else:
                        error.set_text(t("auth.login_failed"))
                    return

                login_rate_limiter.clear(rate_key)
                login_session(user_id=user_id, username=name)
                ui.navigate.to(target)

            password.on("keydown.enter", _submit)
            ui.button(
                t("auth.login_button"),
                icon="login",
                on_click=_submit,
            ).props("color=primary unelevated").classes(f"w-full {AUTH_CONTROL}")

        return None
