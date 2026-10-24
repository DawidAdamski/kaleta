# SPDX-License-Identifier: AGPL-3.0-or-later
"""Login page — through whichever ``AuthProvider`` this install uses.

E-mail + password, with a link to sign up while registration is open; with
``supabase`` also a forgotten-password link and a magic link.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.login_rate_limit import (
    RATE_LIMITER_BACKEND_ERRORS,
    login_email_rate_limiter,
    login_rate_limiter,
)
from kaleta.auth.providers import MfaRequired, get_auth_provider
from kaleta.auth.redirects import safe_redirect
from kaleta.auth.session import (
    begin_hosted_mfa_challenge,
    finish_login,
    is_authenticated,
)
from kaleta.auth.sign_in import SignInFlow, registry_sign_up_state, resend_confirmation
from kaleta.exceptions import EmailNotVerifiedError, KaletaError, UnauthorizedError
from kaleta.i18n import t

if TYPE_CHECKING:
    pass

from kaleta.views.auth_common import (
    auth_action,
    auth_error_slot,
    auth_field,
    auth_link,
    auth_page_shell,
    auth_submit,
)

logger = logging.getLogger(__name__)


def _client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def _rate_limiter_unavailable() -> None:
    """Toast shown when the rate limiter's backend (Redis) cannot be reached.

    The limiter fails closed on purpose, so the sign-in does not proceed — but
    a dead click with nothing said is worse than a sentence that asks the user
    to try again once the backend is back.
    """
    ui.notify(t("common.rate_limit_unavailable"), type="warning")


def register() -> None:
    @ui.page("/login")
    async def login_page(
        request: Request,
        redirect_to: str = "/",
        reason: str = "",
    ) -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse(safe_redirect(redirect_to))

        # Every backend signs in by e-mail; only Supabase also sends mail.
        provider = get_auth_provider()
        sends_mail = provider.name == "supabase"

        # No family to ask before someone signs in; with local logins an empty
        # instance's first run is the administrator's sign-up.
        signup = await registry_sign_up_state()
        if signup.first_run:
            return RedirectResponse("/create-account")

        target = safe_redirect(redirect_to)
        rate_key = _client_key(request)
        subtitle = "auth.login_subtitle_hosted"
        shell = await auth_page_shell("auth.login_title", subtitle)

        # `AUTH_CONTROL` is `min-h-[48px]`, shared by all three auth pages: on
        # a phone this form is the whole screen, and a 40px field in the
        # middle of it is a target the thumb has to aim at.
        with shell, ui.column().classes("w-full gap-4"):
            username = auth_field("auth.email").props("autofocus")
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
                try:
                    if login_rate_limiter.is_locked(rate_key):
                        secs = login_rate_limiter.remaining_lock_seconds(rate_key)
                        _say(t("auth.login_rate_limited", seconds=secs))
                        return
                except RATE_LIMITER_BACKEND_ERRORS:
                    # Can't reach the counter to know whether this IP is locked,
                    # so fail closed: do not sign in, say so.
                    _rate_limiter_unavailable()
                    return

                name = (username.value or "").strip()
                pwd = password.value or ""
                # Normalised e-mail key. The second limiter bounds guessing one
                # e-mail from many client addresses, which the IP limiter above
                # cannot see. Skipped when the field is empty — nothing to key on.
                email_key = name.lower()

                if name:
                    try:
                        if login_email_rate_limiter.is_locked(email_key):
                            secs = login_email_rate_limiter.remaining_lock_seconds(email_key)
                            _say(t("auth.login_rate_limited", seconds=secs))
                            return
                    except RATE_LIMITER_BACKEND_ERRORS:
                        # Same fail-closed as the IP pre-check: can't reach the
                        # counter, so do not sign in, say so.
                        _rate_limiter_unavailable()
                        return

                resend.set_visibility(False)
                try:
                    result = await get_auth_provider().sign_in(name, pwd)
                except EmailNotVerifiedError:
                    # Right password: not a failure the rate limiter counts.
                    _say(t("auth.email_not_verified"))
                    resend.set_visibility(True)
                    return
                except UnauthorizedError:
                    try:
                        locked_ip = login_rate_limiter.record_failure(rate_key)
                        locked_email = bool(name) and login_email_rate_limiter.record_failure(
                            email_key
                        )
                        if locked_ip or locked_email:
                            # Either bucket may be the one that just locked; show
                            # the longer remaining lock so the sentence does not
                            # under-report the wait.
                            secs_ip = (
                                login_rate_limiter.remaining_lock_seconds(rate_key)
                                if locked_ip
                                else 0
                            )
                            secs_email = (
                                login_email_rate_limiter.remaining_lock_seconds(email_key)
                                if locked_email
                                else 0
                            )
                            _say(t("auth.login_rate_limited", seconds=max(secs_ip, secs_email)))
                        else:
                            _say(t("auth.login_failed_email"))
                    except RATE_LIMITER_BACKEND_ERRORS:
                        _rate_limiter_unavailable()
                    return
                except KaletaError as exc:
                    _say(exc.message)
                    return

                try:
                    login_rate_limiter.clear(rate_key)
                    if name:
                        login_email_rate_limiter.clear(email_key)
                except RATE_LIMITER_BACKEND_ERRORS:
                    # The password was right; clearing the counters is cleanup,
                    # not a gate. A backend that is down now is no reason to
                    # refuse a sign-in that already succeeded.
                    logger.warning(
                        "Rate limiter backend unreachable while clearing login counter",
                        exc_info=True,
                    )
                if isinstance(result, MfaRequired):
                    # The session stays unauthenticated until the code lands:
                    # a half-finished login must not open a single data page.
                    # The provider holds the factor; its aal1 session is what
                    # the code gets checked against.
                    begin_hosted_mfa_challenge(result)
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
            if signup.open:
                auth_link("auth.sign_up_link", "/create-account")

        return None
