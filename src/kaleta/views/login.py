# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login page — through whichever ``AuthProvider`` this install uses.

Self-hosted (``local``): username + password against the single app user,
exactly as before. Hosted (``supabase``): e-mail + password, with links to
sign up and to reset a forgotten password.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.login_rate_limit import login_rate_limiter
from kaleta.auth.providers import MfaRequired, get_auth_provider
from kaleta.auth.redirects import safe_redirect
from kaleta.auth.session import (
    begin_hosted_mfa_challenge,
    begin_mfa_challenge,
    finish_login,
    is_authenticated,
)
from kaleta.auth.sign_in import SignInFlow, resend_confirmation
from kaleta.config import settings
from kaleta.exceptions import EmailNotVerifiedError, KaletaError, UnauthorizedError
from kaleta.i18n import t
from kaleta.services import AuthService, with_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.views.auth_common import (
    auth_action,
    auth_error_slot,
    auth_field,
    auth_link,
    auth_page_shell,
    auth_submit,
)


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def register() -> None:
    @ui.page("/login")
    async def login_page(
        request: Request,
        redirect_to: str = "/",
        reason: str = "",
    ) -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse(safe_redirect(redirect_to))

        # Any provider but `local` signs people up by e-mail; only Supabase
        # also sends mail (the debug `fake` backend confirms at sign-up).
        hosted = get_auth_provider().name != "local"
        sends_mail = get_auth_provider().name == "supabase"

        async def _bootstrap(session: AsyncSession) -> str | None:
            state = await AuthService(session).auth_state()
            if state == "no_user":
                return "/create-account"
            if state == "placeholder":
                return "/secure-app"
            return None

        # A hosted instance has no "first user" to create and no tenant to ask
        # before someone signs in.
        bootstrap = None if settings.tenancy == "multi" else await with_session(_bootstrap)
        if bootstrap is not None:
            return RedirectResponse(bootstrap)

        target = safe_redirect(redirect_to)
        rate_key = _client_key(request)
        subtitle = "auth.login_subtitle_hosted" if hosted else "auth.login_subtitle"
        shell = await auth_page_shell("auth.login_title", subtitle)

        # `AUTH_CONTROL` is `min-h-[48px]`, shared by all three auth pages: on
        # a phone this form is the whole screen, and a 40px field in the
        # middle of it is a target the thumb has to aim at.
        with shell, ui.column().classes("w-full gap-4"):
            username = auth_field("auth.email" if hosted else "auth.username").props("autofocus")
            password = auth_field("auth.password", password=True, password_toggle_button=True).on(
                "keydown.enter", lambda: None
            )
            _say = auth_error_slot()
            if reason == "mfa_expired":
                # Sent here by the code prompt after the challenge aged out.
                _say(t("auth.mfa_expired"))
            elif reason == "mfa_gone":
                # Sent here by the code prompt when the factor it was asking
                # for stopped existing underneath it.
                _say(t("auth.mfa_gone"))
            elif reason == "idle":
                # Sent here by the auth guard after the idle window ran out.
                _say(t("auth.reason_idle"))
            elif reason == "signed_out_everywhere":
                # Sent here by the auth guard after a credential change (or
                # "Sign out everywhere") revoked this browser's session.
                _say(t("auth.reason_signed_out_everywhere"))
            elif reason == "verified":
                # Sent here by the verification link in the sign-up e-mail.
                _say(t("auth.reason_verified"))
            elif reason == "password_reset":
                _say(t("auth.reason_password_reset"))
            elif reason == "link_expired":
                # Sent here by /auth/magic when the sign-in link was stale.
                _say(t("auth.reason_link_expired"))
            elif reason == "link_failed":
                _say(t("auth.reason_link_failed"))

            async def _submit() -> None:
                _say("")
                if login_rate_limiter.is_locked(rate_key):
                    secs = login_rate_limiter.remaining_lock_seconds(rate_key)
                    _say(t("auth.login_rate_limited", seconds=secs))
                    return

                name = (username.value or "").strip()
                pwd = password.value or ""

                resend.set_visibility(False)
                try:
                    result = await get_auth_provider().sign_in(name, pwd)
                except EmailNotVerifiedError:
                    # Right password: not a failure the rate limiter counts.
                    _say(t("auth.email_not_verified"))
                    resend.set_visibility(hosted)
                    return
                except UnauthorizedError:
                    locked = login_rate_limiter.record_failure(rate_key)
                    if locked:
                        secs = login_rate_limiter.remaining_lock_seconds(rate_key)
                        _say(t("auth.login_rate_limited", seconds=secs))
                    else:
                        _say(t("auth.login_failed_email" if hosted else "auth.login_failed"))
                    return
                except KaletaError as exc:
                    _say(exc.message)
                    return

                login_rate_limiter.clear(rate_key)
                if isinstance(result, MfaRequired):
                    # The session stays unauthenticated until the code lands:
                    # a half-finished login must not open a single data page.
                    if hosted:
                        # The provider holds the factor; its aal1 session is
                        # what the code gets checked against.
                        begin_hosted_mfa_challenge(result)
                    else:
                        begin_mfa_challenge(
                            user_id=int(result.identity.subject), username=result.identity.email
                        )
                    ui.navigate.to(f"/login/mfa?redirect_to={quote(target, safe='/')}")
                    return
                try:
                    signed_in = await SignInFlow().complete(result)
                except KaletaError as exc:
                    _say(exc.message)
                    return
                finish_login(
                    user_id=signed_in.user_id,
                    username=signed_in.username,
                    target=signed_in.target(target),
                    tenant=signed_in.tenant,
                )

            async def _resend() -> None:
                address = (username.value or "").strip()
                if not address:
                    _say(t("auth.email_required"))
                    return
                try:
                    await resend_confirmation(address)
                except KaletaError as exc:
                    _say(exc.message)
                    return
                _say(t("auth.resend_sent"))

            async def _magic_link() -> None:
                _say("")
                address = (username.value or "").strip()
                if not address:
                    _say(t("auth.email_required"))
                    return
                try:
                    await get_auth_provider().request_magic_link(address)
                except KaletaError as exc:
                    _say(exc.message)
                    return
                _say(t("auth.magic_link_sent"))

            # Shown only after a sign-in was refused for an unconfirmed address.
            resend = auth_action("auth.resend_button", _resend)
            resend.set_visibility(False)

            password.on("keydown.enter", _submit)
            auth_submit("auth.login_button", _submit)
            if sends_mail:
                with ui.row().classes("w-full justify-between gap-2"):
                    auth_link("auth.forgot_password", "/reset-password")
                    auth_action("auth.magic_link_button", _magic_link)
            if hosted:
                auth_link("auth.sign_up_link", "/create-account")

        return None
