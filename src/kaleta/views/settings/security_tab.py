# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Security tab (two-factor authentication, API bearer tokens)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from nicegui import app, ui

from kaleta.auth.login_rate_limit import mfa_rate_limiter
from kaleta.auth.session import SESSION_USER_ID, mark_mfa_verified, mfa_verified_at
from kaleta.exceptions import ConflictError, EncryptionError, KaletaError, ValidationError
from kaleta.i18n import plural_key, t
from kaleta.services import ApiTokenService, MfaEnrolment, MfaService, MfaStatus, with_session
from kaleta.views.error_handling import notify_kaleta_error

#: Redraw the two-factor card after something changed underneath it. NiceGUI's
#: ``refreshable.refresh`` hands back an awaitable these callers do not want,
#: so the return type is the widest thing that says "ignored".
Refresh = Callable[[], object]


async def render_security_tab() -> None:
    user_id = app.storage.user.get(SESSION_USER_ID)
    if user_id is None:
        ui.label(t("settings.security_login_required")).classes("text-slate-500")
        return

    await _render_mfa_card(int(user_id))
    await _render_token_card(int(user_id))


# ── Two-factor authentication ─────────────────────────────────────────────────


async def _mfa_status(user_id: int) -> MfaStatus:
    async def _load(session: Any) -> MfaStatus:
        return await MfaService(session).status(user_id)

    return await with_session(_load)


async def _step_up(user_id: int) -> bool:
    """Make sure a code was given recently. True when the caller may proceed.

    With MFA off there is nothing to prove. With MFA on and the last code older
    than the step-up window, this asks for one and remembers the answer, so a
    run of token edits does not turn into a run of dialogs.
    """

    async def _needed(session: Any) -> bool:
        return await MfaService(session).step_up_required(user_id, mfa_verified_at())

    if not await with_session(_needed):
        return True
    if not await _ask_for_code(user_id):
        return False
    mark_mfa_verified()
    return True


async def _ask_for_code(user_id: int) -> bool:
    """A modal that closes only on a correct code (or a cancel).

    Rate-limited on the same counter as the login prompt. A step-up dialog
    sits behind an already-authenticated session, which is exactly the
    situation — borrowed device, stolen cookie — where an attacker would
    otherwise have unlimited guesses at six digits.
    """
    rate_key = str(user_id)
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-sm"):
        ui.label(t("settings.mfa_step_up_title")).classes("text-lg font-semibold mb-1")
        ui.label(t("settings.mfa_step_up_hint")).classes("text-sm text-slate-500 mb-4")
        code_input = ui.input(label=t("settings.mfa_code")).classes("w-full")
        error = ui.label("").classes("text-sm text-negative mt-2")

        async def _confirm() -> None:
            if mfa_rate_limiter.is_locked(rate_key):
                secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                return
            entered = (code_input.value or "").strip()
            if not entered:
                error.set_text(t("settings.mfa_code_required"))
                return

            async def _verify(session: Any) -> bool | None:
                service = MfaService(session)
                # None means the factor stopped existing between the check
                # that opened this dialog and this submit. `verify_challenge`
                # folds that into the same False as a wrong code, and the two
                # must not cost the same — see the branch below.
                if not await service.is_enabled(user_id):
                    return None
                return await service.verify_challenge(user_id, entered)

            try:
                passed = await with_session(_verify)
            except EncryptionError:
                # A secret written under a different KALETA_SECRET_KEY cannot
                # be checked at all. That is not a wrong guess, so it does not
                # count toward the lockout — and it must not leave the dialog
                # sitting there with nothing said.
                error.set_text(t("settings.mfa_unreadable"))
                return
            except KaletaError as exc:
                error.set_text(exc.message)
                return

            if passed is None:
                # Nothing to prove any more, and nothing the user did wrong.
                # The message goes to a toast rather than the error label,
                # because this dialog is about to close: leaving it open on a
                # prompt no code can satisfy would make Cancel the only way
                # out, which is what `/login/mfa` avoids by navigating away.
                ui.notify(t("settings.mfa_stale"), type="warning")
                dialog.submit(False)
                return
            if not passed:
                if mfa_rate_limiter.record_failure(rate_key):
                    secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                    error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                else:
                    error.set_text(t("settings.mfa_failed"))
                code_input.value = ""
                return
            mfa_rate_limiter.clear(rate_key)
            dialog.submit(True)

        code_input.on("keydown.enter", _confirm)
        with ui.row().classes("gap-2 mt-4 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(t("settings.mfa_confirm"), on_click=_confirm).props("color=primary")

    result = await dialog
    dialog.delete()
    return bool(result)


async def _render_mfa_card(user_id: int) -> None:
    with ui.card().classes("p-6 w-full mb-6"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("phonelink_lock", color="primary").classes("text-xl")
            ui.label(t("settings.mfa_title")).classes("text-lg font-semibold")
        ui.label(t("settings.mfa_hint")).classes("text-xs text-slate-500 mb-4")

        @ui.refreshable
        async def body() -> None:
            status = await _mfa_status(user_id)
            with ui.row().classes("items-center gap-3 mb-4"):
                ui.icon(
                    "verified_user" if status.enabled else "gpp_maybe",
                    color="positive" if status.enabled else "warning",
                )
                if status.enabled and status.enabled_at is not None:
                    ui.label(
                        t(
                            "settings.mfa_status_enabled",
                            date=status.enabled_at.strftime("%Y-%m-%d"),
                        )
                    ).classes("text-sm")
                    remaining = status.recovery_codes_remaining
                    ui.label(
                        t(plural_key("settings.mfa_recovery_remaining", remaining), count=remaining)
                    ).classes("text-xs text-slate-500")
                else:
                    ui.label(t("settings.mfa_status_disabled")).classes("text-sm")

            with ui.row().classes("gap-2 flex-wrap"):
                if not status.enabled:
                    ui.button(
                        t("settings.mfa_setup"),
                        icon="qr_code_2",
                        on_click=lambda: _open_setup(user_id, body.refresh),
                    ).props("color=primary")
                    return
                ui.button(
                    t("settings.mfa_recovery_codes"),
                    icon="password",
                    on_click=lambda: _open_recovery(user_id, body.refresh),
                ).props("outline")
                ui.button(
                    t("settings.mfa_disable"),
                    icon="lock_open",
                    on_click=lambda: _open_disable(user_id, body.refresh),
                ).props("flat color=negative")

        await body()


async def _open_setup(user_id: int, refresh: Refresh) -> None:
    async def _begin(session: Any) -> MfaEnrolment:
        return await MfaService(session).begin_enrolment(user_id)

    try:
        enrolment = await with_session(_begin)
    except ConflictError:
        # Another tab confirmed an enrolment meanwhile, so the card behind
        # this toast is showing a stale "Off" and a button that would fail
        # the same way. Anticipated here, so it gets a localized sentence
        # rather than the service's English literal.
        ui.notify(t("settings.mfa_stale"), type="warning")
        refresh()
        return
    except KaletaError as exc:
        notify_kaleta_error(exc)
        refresh()
        return

    rate_key = str(user_id)
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md"):
        ui.label(t("settings.mfa_setup_title")).classes("text-lg font-semibold mb-2")
        ui.label(t("settings.mfa_setup_step_scan")).classes("text-sm text-slate-500 mb-3")
        ui.html(enrolment.qr_svg).classes("w-48 h-48 self-center")
        ui.label(t("settings.mfa_setup_manual")).classes("text-xs text-slate-500 mt-3")
        ui.label(enrolment.secret).classes("font-mono text-sm break-all select-all")
        ui.label(t("settings.mfa_setup_confirm_hint")).classes("text-sm mt-4")
        code_input = ui.input(label=t("settings.mfa_code")).classes("w-full")
        error = ui.label("").classes("text-sm text-negative mt-2")

        async def _confirm() -> None:
            # Guessing here gains an attacker nothing — whoever opened this
            # dialog already has the secret on screen. The counter is here
            # because each wrong code writes an `mfa_enrol_failure` row, and a
            # prompt that never locks is a way to pump the audit log.
            if mfa_rate_limiter.is_locked(rate_key):
                secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                return
            entered = (code_input.value or "").strip()
            if not entered:
                error.set_text(t("settings.mfa_code_required"))
                return

            async def _do(session: Any) -> list[str]:
                return await MfaService(session).confirm_enrolment(user_id, entered)

            try:
                codes = await with_session(_do)
            except ValidationError:
                # Only a wrong code counts. A dialog gone stale — another tab
                # confirmed the same enrolment, or a shell dropped the pending
                # row — is a `ConflictError`, and this bucket is the one
                # guarding the login prompt, so spending it on that would be a
                # lockout nobody could avoid.
                if mfa_rate_limiter.record_failure(rate_key):
                    secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                    error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                else:
                    error.set_text(t("settings.mfa_enrol_failed"))
                code_input.value = ""
                return
            except ConflictError:
                error.set_text(t("settings.mfa_stale"))
                return
            except EncryptionError:
                error.set_text(t("settings.mfa_unreadable"))
                return
            except KaletaError as exc:
                error.set_text(exc.message)
                return
            mfa_rate_limiter.clear(rate_key)
            dialog.submit(codes)

        code_input.on("keydown.enter", _confirm)
        with ui.row().classes("gap-2 mt-4 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(None)).props("flat")
            ui.button(t("settings.mfa_confirm"), on_click=_confirm).props("color=primary")

    codes = await dialog
    dialog.delete()
    if not codes:
        # Cancelled, or given up on. The pending row holds a live secret and
        # nothing else in the UI can reach it, so it goes with the dialog.
        async def _abandon(session: Any) -> bool:
            return await MfaService(session).abandon_enrolment(user_id)

        await with_session(_abandon)
        refresh()
        return
    mark_mfa_verified()
    ui.notify(t("settings.mfa_enabled_notify"), type="positive")
    await _show_recovery_codes(codes)
    refresh()


async def _open_recovery(user_id: int, refresh: Refresh) -> None:
    if not await _step_up(user_id):
        return

    async def _regenerate(session: Any) -> list[str]:
        return await MfaService(session).regenerate_recovery_codes(
            user_id,
            mfa_verified_at=mfa_verified_at(),
        )

    try:
        codes = await with_session(_regenerate)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        refresh()
        return
    await _show_recovery_codes(codes)
    refresh()


async def _show_recovery_codes(codes: list[str]) -> None:
    joined = "\n".join(codes)
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md"):
        ui.label(t("settings.mfa_recovery_title")).classes("text-lg font-semibold mb-2")
        ui.label(t("settings.mfa_recovery_hint")).classes("text-sm text-slate-500 mb-4")
        with ui.column().classes("gap-1 font-mono text-sm"):
            for code in codes:
                ui.label(code).classes("select-all")
        with ui.row().classes("gap-2 mt-4 justify-end w-full"):
            ui.button(
                t("settings.mfa_copy_codes"),
                icon="content_copy",
                on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText({json.dumps(joined)})"
                ),
            ).props("outline")
            ui.button(t("common.close"), on_click=lambda: dialog.submit(True)).props("flat")
    await dialog
    dialog.delete()


async def _open_disable(user_id: int, refresh: Refresh) -> None:
    """Turning the factor off is guessable twice over, so it is throttled too.

    The service answers a wrong password and a wrong code with the same
    sentence; this counter is what stops an attacker at a signed-in browser
    from simply asking often enough.
    """
    rate_key = str(user_id)
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-sm"):
        ui.label(t("settings.mfa_disable_title")).classes("text-lg font-semibold mb-1")
        ui.label(t("settings.mfa_disable_hint")).classes("text-sm text-slate-500 mb-4")
        password_input = ui.input(label=t("settings.mfa_password"), password=True).classes("w-full")
        code_input = ui.input(label=t("settings.mfa_code")).classes("w-full")
        error = ui.label("").classes("text-sm text-negative mt-2")

        async def _confirm() -> None:
            if mfa_rate_limiter.is_locked(rate_key):
                secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                return

            async def _do(session: Any) -> None:
                await MfaService(session).disable(
                    user_id,
                    password=password_input.value or "",
                    code=code_input.value or "",
                )

            try:
                await with_session(_do)
            except ValidationError:
                # Only a wrong credential counts. A stale dialog — the factor
                # was turned off in another tab — is a `ConflictError`, and
                # locking someone out for that would be a lockout they had no
                # way to avoid. One message for both halves, as the service
                # gives it: telling a wrong password from a wrong code here
                # would make this dialog a password oracle.
                if mfa_rate_limiter.record_failure(rate_key):
                    secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
                    error.set_text(t("settings.mfa_rate_limited", seconds=secs))
                else:
                    error.set_text(t("settings.mfa_disable_failed"))
                code_input.value = ""
                return
            except ConflictError:
                error.set_text(t("settings.mfa_stale"))
                return
            except EncryptionError:
                error.set_text(t("settings.mfa_unreadable"))
                return
            except KaletaError as exc:
                error.set_text(exc.message)
                return
            mfa_rate_limiter.clear(rate_key)
            dialog.submit(True)

        password_input.on("keydown.enter", _confirm)
        code_input.on("keydown.enter", _confirm)
        with ui.row().classes("gap-2 mt-4 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(t("settings.mfa_disable"), on_click=_confirm).props("color=negative")

    disabled = await dialog
    dialog.delete()
    if disabled:
        ui.notify(t("settings.mfa_disabled_notify"), type="positive")
    refresh()


# ── API bearer tokens ─────────────────────────────────────────────────────────


async def _render_token_card(user_id: int) -> None:
    token_dialog = ui.dialog()
    created_token: dict[str, str] = {"value": ""}

    with token_dialog, ui.card().classes("p-6 w-full max-w-lg"):
        ui.label(t("settings.security_token_created_title")).classes("text-lg font-semibold mb-2")
        ui.label(t("settings.security_token_created_hint")).classes("text-sm text-slate-500 mb-4")
        token_field = (
            ui.input(
                label=t("settings.security_token_value"),
                value="",
            )
            .props("readonly")
            .classes("w-full font-mono")
        )
        with ui.row().classes("gap-2 mt-4"):
            ui.button(
                t("settings.security_copy_token"),
                icon="content_copy",
                on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText({json.dumps(created_token['value'])})"
                ),
            ).props("outline")
            ui.button(t("common.close"), on_click=token_dialog.close).props("flat")

    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("vpn_key", color="primary").classes("text-xl")
            ui.label(t("settings.security_api_tokens")).classes("text-lg font-semibold")
        ui.label(t("settings.security_api_tokens_hint")).classes("text-xs text-slate-500 mb-4")

        label_input = ui.input(
            label=t("settings.security_token_label"),
            placeholder=t("settings.security_token_label_placeholder"),
        ).classes("w-full max-w-md")

        async def _create_token() -> None:
            label = (label_input.value or "").strip()
            if not label:
                ui.notify(t("settings.security_token_label_required"), type="warning")
                return
            if not await _step_up(user_id):
                # Either a wrong code, which the dialog already explained, or
                # a cancel, which needs no explaining at all.
                return

            async def _create(session: Any) -> tuple[str, str]:
                token, raw = await ApiTokenService(session).create_token(
                    user_id=user_id,
                    label=label,
                    mfa_verified_at=mfa_verified_at(),
                )
                return token.label, raw

            try:
                _label, raw = await with_session(_create)
            except KaletaError as exc:
                # Minting a token now needs a fresh step-up, so this call has a
                # domain failure it did not have before, with a message meant
                # to be read. The bare arm below is for the ones that are not.
                notify_kaleta_error(exc)
                return
            except Exception as exc:
                ui.notify(
                    t("settings.security_token_create_failed", error=str(exc)),
                    type="negative",
                )
                return

            label_input.value = ""
            created_token["value"] = raw
            token_field.value = raw
            token_dialog.open()
            ui.notify(t("settings.security_token_created"), type="positive")
            tokens_table.refresh()

        ui.button(
            t("settings.security_create_token"),
            icon="add",
            on_click=_create_token,
        ).props("color=primary").classes("mb-6")

        @ui.refreshable
        async def tokens_table() -> None:
            async def _load(session: Any) -> list[Any]:
                return await ApiTokenService(session).list_tokens(user_id=user_id)

            tokens = await with_session(_load)
            if not tokens:
                ui.label(t("settings.security_no_tokens")).classes("text-slate-400 text-sm")
                return

            cols = [
                {
                    "name": "label",
                    "label": t("settings.security_col_label"),
                    "field": "label",
                    "align": "left",
                },
                {
                    "name": "created",
                    "label": t("settings.security_col_created"),
                    "field": "created",
                    "align": "left",
                },
                {
                    "name": "last_used",
                    "label": t("settings.security_col_last_used"),
                    "field": "last_used",
                    "align": "left",
                },
                {
                    "name": "status",
                    "label": t("settings.security_col_status"),
                    "field": "status",
                    "align": "left",
                },
                {
                    "name": "actions",
                    "label": "",
                    "field": "id",
                    "align": "right",
                },
            ]
            rows = [
                {
                    "id": token.id,
                    "label": token.label,
                    "created": token.created_at.strftime("%Y-%m-%d %H:%M"),
                    "last_used": (
                        token.last_used_at.strftime("%Y-%m-%d %H:%M")
                        if token.last_used_at
                        else t("settings.security_never_used")
                    ),
                    "status": (
                        t("settings.security_status_active")
                        if token.is_active
                        else t("settings.security_status_revoked")
                    ),
                    "revoked": not token.is_active,
                }
                for token in tokens
            ]
            table = (
                ui.table(columns=cols, rows=rows, row_key="id")
                .classes("w-full")
                .props("flat dense")
            )

            async def _revoke(token_id: int) -> None:
                if not await _step_up(user_id):
                    return

                async def _do_revoke(session: Any) -> None:
                    await ApiTokenService(session).revoke_token(
                        token_id=token_id,
                        user_id=user_id,
                        mfa_verified_at=mfa_verified_at(),
                    )

                try:
                    await with_session(_do_revoke)
                except KaletaError as exc:
                    # The factor may have been switched on in another tab since
                    # the step-up check above said it was off.
                    notify_kaleta_error(exc)
                    return
                ui.notify(t("settings.security_token_revoked"), type="positive")
                tokens_table.refresh()

            table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                  <q-btn v-if="!props.row.revoked"
                         flat dense round icon="block" size="sm"
                         color="negative"
                         @click="$emit('revoke', props.row)" />
                </q-td>
                """,
            )
            table.on("revoke", lambda e: _revoke(int(e.args["id"])))

        await tokens_table()
