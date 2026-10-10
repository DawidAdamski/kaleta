# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account creation, through whichever ``AuthProvider`` this install uses.

Self-hosted (``local``): the first-run page, only while the database has no
user row. Hosted (``supabase``): sign-up with an e-mail address, which ends in
"check your inbox" — the account itself is provisioned at the first sign-in
after the address is confirmed.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import finish_login, is_authenticated
from kaleta.auth.sign_in import SignInFlow, registry_sign_up_state, resend_confirmation
from kaleta.config import settings
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.views.auth_common import (
    auth_action,
    auth_error_slot,
    auth_field,
    auth_link,
    auth_page_shell,
    auth_submit,
)
from kaleta.views.theme import AUTH_SUBTITLE


def register() -> None:
    @ui.page("/create-account")
    async def create_account_page() -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse("/")

        provider = get_auth_provider()
        # The administrator's sign-up on an empty instance, afterwards only
        # while registration is open (ADR-38).
        signup = await registry_sign_up_state()
        if not signup.open:
            return RedirectResponse("/login")

        if signup.first_run:
            shell = await auth_page_shell("auth.admin_title", "auth.admin_subtitle")
        else:
            # Local logins send no confirmation mail.
            subtitle = "auth.signup_subtitle_local" if provider.name == "local" else None
            shell = await auth_page_shell("auth.signup_title", subtitle or "auth.signup_subtitle")

        with shell, ui.column().classes("w-full gap-4") as form:
            username = auth_field("auth.email").props("autofocus")
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
                    _say(t("auth.email_required"))
                    return
                if len(pwd) < 8:
                    _say(t("auth.password_too_short"))
                    return
                if pwd != pwd2:
                    _say(t("auth.password_mismatch"))
                    return

                try:
                    result = await provider.sign_up(name, pwd)
                    if result.identity is None:
                        _show_check_inbox(name)
                        return
                    signed_in = await SignInFlow().complete(result.identity)
                except KaletaError as exc:
                    _say(exc.message)
                    return

                finish_login(
                    user_id=signed_in.user_id,
                    username=signed_in.username,
                    target="/wizard",
                    tenant=signed_in.tenant,
                )

            def _show_check_inbox(address: str) -> None:
                form.clear()
                with form:
                    ui.label(t("auth.check_inbox_title")).classes("text-lg font-semibold")
                    ui.label(t("auth.check_inbox_body")).classes(AUTH_SUBTITLE)
                    if settings.encryption_enabled:
                        # Step 2 of the sign-up (hosted-field-encryption): it
                        # happens at the first sign-in, on /unlock.
                        ui.label(t("auth.check_inbox_passphrase")).classes(AUTH_SUBTITLE)
                    _say_sent = auth_error_slot()

                    async def _resend() -> None:
                        try:
                            await resend_confirmation(address)
                        except KaletaError as exc:
                            _say_sent(exc.message)
                            return
                        _say_sent(t("auth.resend_sent"))

                    auth_action("auth.resend_button", _resend)
                    auth_link("auth.have_account_link", "/login")

            confirm.on("keydown.enter", _submit)
            auth_submit("auth.signup_button", _submit)
            if not signup.first_run:
                auth_link("auth.have_account_link", "/login")

        return None
