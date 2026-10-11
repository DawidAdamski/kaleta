# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/join?token=…``: where an invitation link to a household lands.

``hosted-household-sharing`` §2. The link carries no key material — only the
proof that its address was invited. With ``local`` logins the invitee chooses
a password here, which creates the login for that address alone, and is signed
in and sent on to ``/unlock`` to set their data passphrase. With Supabase Auth
the provider holds the logins: the page points to sign-up and sign-in with the
invited address, and the first verified sign-in joins the household.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.household import accept_invitation, preview_invitation
from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import finish_login, is_authenticated
from kaleta.auth.sign_in import SignInFlow
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.identity import Identity
from kaleta.views.auth_common import (
    auth_error_slot,
    auth_field,
    auth_link,
    auth_page_shell,
    auth_submit,
)
from kaleta.views.theme import AUTH_SUBTITLE

JOIN_PATH = "/join"
#: The local sign-up's rule, kept the same here.
PASSWORD_MIN_LENGTH = 8


def register() -> None:
    @ui.page(JOIN_PATH)
    async def join_page(token: str = "") -> RedirectResponse | None:
        if is_authenticated():
            # A signed-in browser belongs to its own household already.
            return RedirectResponse("/")
        invitation = await preview_invitation(token) if token else None
        if invitation is None:
            shell = await auth_page_shell("household.join_gone_title", "household.join_gone")
            with shell:
                auth_link("auth.have_account_link", "/login")
            return None

        shell = await auth_page_shell("household.join_title", "household.join_subtitle")
        with shell, ui.column().classes("w-full gap-4"):
            ui.label(invitation.email).classes("text-base font-semibold").props(
                'data-testid="join-email"'
            )
            if get_auth_provider().name == "local":
                _password_form(token, invitation.email)
            else:
                ui.label(t("household.join_hosted", email=invitation.email)).classes(AUTH_SUBTITLE)
                auth_link("auth.signup_button", "/create-account")
                auth_link("auth.have_account_link", "/login")
        return None


def _password_form(token: str, email: str) -> None:
    password = auth_field("auth.password", password=True, password_toggle_button=True).props(
        "autofocus"
    )
    confirm = auth_field("auth.password_confirm", password=True, password_toggle_button=True)
    say = auth_error_slot()

    async def _submit() -> None:
        say("")
        value = password.value or ""
        if len(value) < PASSWORD_MIN_LENGTH:
            say(t("auth.password_too_short"))
            return
        if value != (confirm.value or ""):
            say(t("auth.password_mismatch"))
            return
        button.disable()
        try:
            await accept_invitation(token, value)
            result = await get_auth_provider().sign_in(email, value)
            if not isinstance(result, Identity):
                # A fresh login has no second factor; anything else signs in as usual.
                ui.navigate.to("/login")
                return
            signed_in = await SignInFlow().complete(result)
        except KaletaError as exc:
            button.enable()
            say(exc.message)
            return
        finish_login(
            user_id=signed_in.user_id,
            username=signed_in.username,
            target="/unlock",
            tenant=signed_in.tenant,
        )

    confirm.on("keydown.enter", _submit)
    button = auth_submit("household.join_button", _submit)
