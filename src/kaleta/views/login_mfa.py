# SPDX-License-Identifier: AGPL-3.0-or-later
"""The second half of a login: the code from the authenticator app.

Reached only from :mod:`kaleta.views.login` (or, hosted, a magic link), and
only once the first factor has been accepted. Until the code lands the session
carries no authentication at all, so this page is public to the route guard and
guards itself instead.

Two backends behind one page. Locally ``MfaService`` checks the code against
``user_mfa``; hosted, Supabase Auth checks it and ``SignInFlow`` finishes the
sign-in, and a recovery code removes the provider's factor — which the
recovery hint says before anyone spends one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi.responses import RedirectResponse
from nicegui import ui

from kaleta.auth.login_rate_limit import mfa_rate_limiter
from kaleta.auth.redirects import safe_redirect
from kaleta.auth.session import (
    clear_mfa_challenge,
    finish_login,
    hosted_mfa_pending,
    is_authenticated,
    is_hosted_mfa_pending,
    is_mfa_pending,
    mfa_pending_user,
)
from kaleta.auth.sign_in import SignedIn, SignInFlow
from kaleta.exceptions import ConflictError, EncryptionError, KaletaError, ValidationError
from kaleta.i18n import t
from kaleta.services import MfaService, with_session
from kaleta.views.auth_common import (
    AUTH_CONTROL,
    auth_error_slot,
    auth_field,
    auth_page_shell,
    auth_submit,
)
from kaleta.views.theme import AUTH_SUBTITLE

if TYPE_CHECKING:
    from kaleta.schemas.identity import MfaRequired


def _back_to_login(reason: str, target: str) -> str:
    """The sign-in page, told why we are back and where we were going."""
    url = f"/login?reason={reason}"
    if target != "/":
        url += f"&redirect_to={quote(target, safe='/')}"
    return url


def register() -> None:
    @ui.page("/login/mfa")
    async def login_mfa_page(redirect_to: str = "/") -> RedirectResponse | None:
        if is_authenticated():
            return RedirectResponse(safe_redirect(redirect_to))

        # Asked before, because `mfa_pending_user()` clears a stale challenge
        # on its way to answering None — and the difference matters: one of
        # these two cases has something to explain and a destination to keep.
        had_challenge = is_mfa_pending() or is_hosted_mfa_pending()
        hosted = hosted_mfa_pending()
        if hosted is not None:
            await _hosted_prompt(hosted, safe_redirect(redirect_to))
            return None
        pending = mfa_pending_user()
        if pending is None:
            if had_challenge:
                # It existed and aged out. This is the reload that KAL-AUTH-021
                # describes, and the one place the expiry message is most owed.
                return RedirectResponse(_back_to_login("mfa_expired", safe_redirect(redirect_to)))
            # There never was a password step, so there is no code prompt and
            # nothing here to brute force — and nothing to explain either.
            return RedirectResponse("/login")
        user_id, username = pending

        target = safe_redirect(redirect_to)
        rate_key = str(user_id)
        shell = await auth_page_shell("auth.mfa_title", "auth.mfa_subtitle")

        with shell, ui.column().classes("w-full gap-4"):
            with ui.column().classes("w-full gap-0") as code_block:
                code = auth_field("auth.mfa_code").props(
                    'autofocus inputmode="numeric" maxlength="6"'
                )
            with ui.column().classes("w-full gap-0") as recovery_block:
                recovery = auth_field("auth.mfa_recovery_code")
            recovery_block.set_visibility(False)

            _say = auth_error_slot()

            def _use_recovery() -> None:
                code_block.set_visibility(False)
                recovery_block.set_visibility(True)
                switch.set_text(t("auth.mfa_use_code"))
                hint.set_text(t("auth.mfa_recovery_hint"))
                recovery.run_method("focus")

            def _use_code() -> None:
                # The way back. Without it, someone who clicked the link to
                # see what it did could only return by reloading — the one
                # action that can trip the challenge TTL and cost them the
                # password step as well.
                recovery_block.set_visibility(False)
                code_block.set_visibility(True)
                switch.set_text(t("auth.mfa_use_recovery"))
                hint.set_text(t("auth.mfa_hint"))
                code.run_method("focus")

            def _toggle() -> None:
                if recovery_block.visible:
                    _use_code()
                else:
                    _use_recovery()

            async def _submit() -> None:
                _say("")
                # Re-read the challenge rather than trusting the one this page
                # was built from: it may have aged out of its TTL while the
                # prompt sat open, or been cleared by a logout in another tab.
                # Without this the expiry would only ever apply to a reload.
                if mfa_pending_user() != pending:
                    # The reason travels with the redirect: saying it here and
                    # then navigating away shows it to nobody. So does the
                    # destination — someone deep-linked to /transactions
                    # should land there once they have signed in again, not
                    # on the dashboard.
                    ui.navigate.to(_back_to_login("mfa_expired", target))
                    return
                if mfa_rate_limiter.is_locked(rate_key):
                    secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                    _say(t("auth.mfa_rate_limited", seconds=secs))
                    return

                using_recovery = recovery_block.visible
                entered = ((recovery.value if using_recovery else code.value) or "").strip()
                if not entered:
                    _say(t("auth.mfa_code_required"))
                    return

                async def _check(session: Any) -> bool | None:
                    service = MfaService(session)
                    # None means "there is nothing here to answer any more".
                    # Both calls below fold that into a plain False, and this
                    # page has to tell the two apart: see the branch below.
                    if not await service.is_enabled(user_id):
                        return None
                    if using_recovery:
                        return await service.consume_recovery_code(user_id, entered)
                    return await service.verify_code(user_id, entered)

                try:
                    passed = await with_session(_check)
                except EncryptionError:
                    # The secret was written under a different
                    # KALETA_SECRET_KEY. No code will ever match it, and
                    # saying so beats a stack trace and a login that fails
                    # forever for no stated reason.
                    _say(t("auth.mfa_unreadable"))
                    return
                if passed is None:
                    # The factor was turned off in another tab while this
                    # prompt sat open. No code can answer this page now, so
                    # charging a try to the limiter would lock someone out of
                    # a login that has just become password-only.
                    clear_mfa_challenge()
                    ui.navigate.to(_back_to_login("mfa_gone", target))
                    return
                if not passed:
                    if mfa_rate_limiter.record_failure(rate_key):
                        secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                        _say(t("auth.mfa_rate_limited", seconds=secs))
                    else:
                        _say(t("auth.mfa_failed"))
                    code.value = ""
                    recovery.value = ""
                    return

                mfa_rate_limiter.clear(rate_key)
                clear_mfa_challenge()
                finish_login(user_id=user_id, username=username, target=target, mfa_verified=True)

            code.on("keydown.enter", _submit)
            recovery.on("keydown.enter", _submit)
            auth_submit("auth.mfa_verify", _submit)

            switch = (
                ui.button(t("auth.mfa_use_recovery"), on_click=_toggle, color=None)
                .props("flat no-caps dense")
                .classes(f"{AUTH_CONTROL} self-start px-0")
            )
            hint = ui.label(t("auth.mfa_hint")).classes(f"{AUTH_SUBTITLE} text-[13px]")

        return None


async def _hosted_prompt(pending: MfaRequired, target: str) -> None:
    """The same prompt, answered by Supabase Auth (``KALETA_AUTH_BACKEND=supabase``)."""
    rate_key = pending.identity.subject
    shell = await auth_page_shell("auth.mfa_title", "auth.mfa_subtitle")

    with shell, ui.column().classes("w-full gap-4"):
        with ui.column().classes("w-full gap-0") as code_block:
            code = auth_field("auth.mfa_code").props('autofocus inputmode="numeric" maxlength="6"')
        with ui.column().classes("w-full gap-0") as recovery_block:
            recovery = auth_field("auth.mfa_recovery_code")
        recovery_block.set_visibility(False)

        _say = auth_error_slot()

        def _toggle() -> None:
            to_recovery = not recovery_block.visible
            code_block.set_visibility(not to_recovery)
            recovery_block.set_visibility(to_recovery)
            switch.set_text(t("auth.mfa_use_code" if to_recovery else "auth.mfa_use_recovery"))
            # Said before the code is spent, not after: on this backend a
            # recovery code turns the factor off.
            hint.set_text(t("auth.mfa_recovery_hint_hosted" if to_recovery else "auth.mfa_hint"))
            (recovery if to_recovery else code).run_method("focus")

        async def _submit() -> None:
            _say("")
            if hosted_mfa_pending() != pending:
                ui.navigate.to(_back_to_login("mfa_expired", target))
                return
            if mfa_rate_limiter.is_locked(rate_key):
                secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                _say(t("auth.mfa_rate_limited", seconds=secs))
                return

            using_recovery = recovery_block.visible
            entered = ((recovery.value if using_recovery else code.value) or "").strip()
            if not entered:
                _say(t("auth.mfa_code_required"))
                return

            flow = SignInFlow()
            signed_in: SignedIn | None
            try:
                if using_recovery:
                    signed_in = await flow.recover(pending, entered)
                else:
                    signed_in = await flow.verify_code(pending, entered)
            except ValidationError:
                signed_in = None
            except ConflictError:
                # The factor was removed at the provider while the prompt sat
                # open: the password is all this account needs now.
                clear_mfa_challenge()
                ui.navigate.to(_back_to_login("mfa_gone", target))
                return
            except KaletaError as exc:
                _say(exc.message)
                return
            if signed_in is None:
                if mfa_rate_limiter.record_failure(rate_key):
                    secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                    _say(t("auth.mfa_rate_limited", seconds=secs))
                else:
                    _say(t("auth.mfa_failed"))
                code.value = ""
                recovery.value = ""
                return

            mfa_rate_limiter.clear(rate_key)
            clear_mfa_challenge()
            finish_login(
                user_id=signed_in.user_id,
                username=signed_in.username,
                target=signed_in.target(target),
                mfa_verified=True,
                tenant=signed_in.tenant,
            )

        code.on("keydown.enter", _submit)
        recovery.on("keydown.enter", _submit)
        auth_submit("auth.mfa_verify", _submit)

        switch = (
            ui.button(t("auth.mfa_use_recovery"), on_click=_toggle, color=None)
            .props("flat no-caps dense")
            .classes(f"{AUTH_CONTROL} self-start px-0")
        )
        hint = ui.label(t("auth.mfa_hint")).classes(f"{AUTH_SUBTITLE} text-[13px]")
