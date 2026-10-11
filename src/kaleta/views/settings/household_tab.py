# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings → Household: who shares this family's data (``hosted-household-sharing`` §5).

Every member sees the members — name, e-mail, role, status, when they joined
and their key's fingerprint — and may change their own display name or leave.
The owner also invites (a link shown once, to pass on), approves or declines
a pending member, removes one, and hands the household to another member.

Approving asks for the data passphrase again: it seals the household's key to
the newcomer's keypair, and the fingerprint shown is the one sealed to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from nicegui import app, ui

from kaleta.auth.household import (
    approve_member,
    leave_household,
    remove_member,
    with_household,
)
from kaleta.auth.session import SESSION_USER_ID, finish_logout
from kaleta.config import settings
from kaleta.exceptions import KaletaError, ValidationError
from kaleta.i18n import t
from kaleta.services.household_service import (
    HouseholdMember,
    HouseholdService,
    Invitation,
    PendingInvitation,
)
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.settings.security_tab import mfa_step_up

#: Redraw the tab (``ui.refreshable.refresh``; its awaitable is not wanted).
Refresh = Callable[[], object]


@dataclass(frozen=True)
class _Household:
    me_id: int
    is_owner: bool
    members: list[HouseholdMember]
    invitations: list[PendingInvitation]


async def _load() -> _Household:
    async def _read(service: HouseholdService) -> _Household:
        return _Household(
            me_id=service.me.member.id,
            is_owner=service.is_owner,
            members=await service.members(),
            invitations=await service.invitations() if service.is_owner else [],
        )

    return await with_household(_read)


def _day(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value is not None else "—"


def _base_url() -> str:
    if settings.public_url:
        return settings.public_url
    client = ui.context.client
    return str(client.request.base_url) if client.request is not None else ""


async def render_household_tab() -> None:
    @ui.refreshable
    async def _body() -> None:
        try:
            household = await _load()
        except KaletaError as exc:
            ui.label(exc.message).classes("text-slate-500")
            return
        _members_card(household, _body.refresh)
        await _me_card(household)
        if household.is_owner:
            _invite_card(household, _body.refresh)

    await _body()


# ── Members ──────────────────────────────────────────────────────────────────


def _members_card(household: _Household, refresh: Refresh) -> None:
    with ui.card().classes("p-6 w-full mb-6"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("group", color="primary").classes("text-xl")
            ui.label(t("household.members_title")).classes("text-lg font-semibold")
        ui.label(t("household.members_hint", count=settings.household_max_members)).classes(
            "text-xs text-slate-500 mb-4"
        )
        for member in household.members:
            _member_row(member, household, refresh)


def _member_row(member: HouseholdMember, household: _Household, refresh: Refresh) -> None:
    pending = member.is_pending
    with (
        ui.row()
        .classes("w-full items-start justify-between gap-3 py-3 border-b border-slate-200")
        .props(f'data-testid="member-{member.email}"')
    ):
        with ui.column().classes("gap-0 min-w-0"):
            with ui.row().classes("items-center gap-2"):
                ui.label(member.display_name).classes("font-medium")
                ui.badge(
                    t("household.role_owner" if member.is_owner else "household.role_member"),
                    color="primary" if member.is_owner else "grey-6",
                )
                if pending:
                    ui.badge(t("household.status_pending"), color="warning")
                if member.member_id == household.me_id:
                    ui.label(t("household.you")).classes("text-xs text-slate-500")
            ui.label(member.email).classes("text-sm text-slate-500")
            if member.joined_at is not None:
                ui.label(t("household.joined", date=_day(member.joined_at))).classes(
                    "text-xs text-slate-500"
                )
            if member.fingerprint is not None:
                ui.label(member.fingerprint).classes(
                    "font-mono text-xs text-slate-600 break-all"
                ).props(f'data-testid="fingerprint-{member.email}"')
            elif pending and settings.encryption_enabled:
                ui.label(t("household.no_passphrase_yet")).classes("text-xs text-slate-500")
        if household.is_owner and member.member_id != household.me_id:
            with ui.row().classes("gap-2 flex-wrap"):
                if pending:
                    ui.button(
                        t("household.approve"),
                        icon="how_to_reg",
                        on_click=lambda m=member: _approve(m, refresh),
                    ).props("color=primary no-caps").set_enabled(
                        member.has_keys or not settings.encryption_enabled
                    )
                    ui.button(
                        t("household.decline"),
                        on_click=lambda m=member: _decline(m, refresh),
                    ).props("flat no-caps")
                else:
                    ui.button(
                        t("household.make_owner"),
                        on_click=lambda m=member: _make_owner(m, refresh),
                    ).props("outline no-caps")
                    ui.button(
                        t("household.remove"),
                        on_click=lambda m=member: _remove(m, refresh),
                    ).props("flat no-caps color=negative")


async def _approve(member: HouseholdMember, refresh: Refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3"):
        ui.label(t("household.approve_title", email=member.email)).classes("text-lg font-semibold")
        passphrase: ui.input | None = None
        if settings.encryption_enabled:
            ui.label(t("household.approve_compare", email=member.email)).classes(
                "text-sm text-slate-500"
            )
            ui.label(member.fingerprint or "").classes(
                "font-mono text-sm select-all p-3 rounded border border-slate-300 w-full"
            )
            passphrase = ui.input(t("unlock.passphrase"), password=True).classes("w-full")
        error = ui.label("").classes("text-sm text-negative")

        async def _go() -> None:
            try:
                await approve_member(
                    member.member_id,
                    passphrase.value or "" if passphrase is not None else "",
                    member.fingerprint,
                )
            except ValidationError:
                error.set_text(t("unlock.wrong_passphrase"))
                return
            except KaletaError as exc:
                error.set_text(exc.message)
                return
            dialog.submit(True)

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(t("household.approve"), on_click=_go).props("color=primary")
    approved = await dialog
    dialog.delete()
    if approved:
        ui.notify(t("household.approved", email=member.email), type="positive")
        refresh()


async def _decline(member: HouseholdMember, refresh: Refresh) -> None:
    if not await _confirm(
        t("household.decline_title", email=member.email),
        t("household.decline_hint"),
        t("household.decline"),
    ):
        return

    async def _go(service: HouseholdService) -> None:
        await service.decline(member.member_id)

    try:
        await with_household(_go)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    refresh()


async def _make_owner(member: HouseholdMember, refresh: Refresh) -> None:
    if not await _confirm(
        t("household.make_owner_title", email=member.email),
        t("household.make_owner_hint"),
        t("household.make_owner"),
    ):
        return
    user_id = app.storage.user.get(SESSION_USER_ID)
    if user_id is None or not await mfa_step_up(int(user_id)):
        return

    async def _go(service: HouseholdService) -> None:
        await service.transfer_ownership(member.member_id)

    try:
        await with_household(_go)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    ui.notify(t("household.owner_changed", email=member.email), type="positive")
    refresh()


async def _remove(member: HouseholdMember, refresh: Refresh) -> None:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3"):
        ui.label(t("household.remove_title", email=member.email)).classes("text-lg font-semibold")
        ui.label(t("household.remove_hint")).classes("text-sm text-slate-500")
        rekey: ui.switch | None = None
        if settings.encryption_enabled:
            rekey = ui.switch(t("household.remove_rekey"), value=True)
            ui.label(t("household.remove_rekey_hint")).classes("text-xs text-slate-500")
        error = ui.label("").classes("text-sm text-negative")

        async def _go() -> None:
            button.disable()
            try:
                await remove_member(
                    member.member_id, rekey=bool(rekey.value) if rekey is not None else False
                )
            except KaletaError as exc:
                button.enable()
                error.set_text(exc.message)
                return
            dialog.submit(True)

        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            button = ui.button(t("household.remove"), on_click=_go).props("color=negative")
    removed = await dialog
    dialog.delete()
    if removed:
        ui.notify(t("household.removed", email=member.email), type="positive")
        refresh()


async def _confirm(title: str, hint: str, action: str) -> bool:
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-sm gap-3"):
        ui.label(title).classes("text-lg font-semibold")
        ui.label(hint).classes("text-sm text-slate-500")
        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
            ui.button(action, on_click=lambda: dialog.submit(True)).props("color=primary")
    answer = await dialog
    dialog.delete()
    return bool(answer)


# ── Me ───────────────────────────────────────────────────────────────────────


async def _me_card(household: _Household) -> None:
    me = next((m for m in household.members if m.member_id == household.me_id), None)
    with ui.card().classes("p-6 w-full mb-6"):
        with ui.row().classes("items-center gap-2 mb-3"):
            ui.icon("badge", color="primary").classes("text-xl")
            ui.label(t("household.me_title")).classes("text-lg font-semibold")
        with ui.row().classes("items-end gap-2 w-full"):
            name = ui.input(
                t("household.display_name"), value=me.display_name if me is not None else ""
            ).classes("flex-1 min-w-[12rem]")

            async def _save_name() -> None:
                value = name.value or ""

                async def _go(service: HouseholdService) -> None:
                    await service.set_display_name(value)

                try:
                    await with_household(_go)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                ui.notify(t("household.name_saved"), type="positive")

            ui.button(t("common.save"), on_click=_save_name).props("outline no-caps")
        if not household.is_owner:
            ui.button(t("household.leave"), icon="logout", on_click=_leave).props(
                "flat no-caps color=negative"
            ).classes("mt-4")
        else:
            ui.label(t("household.owner_cannot_leave")).classes("text-xs text-slate-500 mt-4")


async def _leave() -> None:
    if not await _confirm(
        t("household.leave_title"), t("household.leave_hint"), t("household.leave")
    ):
        return
    try:
        await leave_household()
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    finish_logout()


# ── Invitations (the owner's) ────────────────────────────────────────────────


def _invite_card(household: _Household, refresh: Refresh) -> None:
    with ui.card().classes("p-6 w-full mb-6"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("person_add", color="primary").classes("text-xl")
            ui.label(t("household.invite_title")).classes("text-lg font-semibold")
        ui.label(t("household.invite_hint")).classes("text-xs text-slate-500 mb-4")
        with ui.row().classes("items-end gap-2 w-full"):
            email = ui.input(t("auth.email")).classes("flex-1 min-w-[12rem]")

            async def _invite() -> None:
                address = (email.value or "").strip()

                async def _go(service: HouseholdService) -> Invitation:
                    return await service.invite(address)

                try:
                    invitation = await with_household(_go)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                email.set_value("")
                await _show_link(invitation)
                refresh()

            ui.button(t("household.invite"), icon="send", on_click=_invite).props(
                "color=primary no-caps"
            )
        if household.invitations:
            ui.label(t("household.open_invitations")).classes("text-sm font-medium mt-4")
            for invitation in household.invitations:
                with ui.row().classes("w-full items-center justify-between gap-2 py-1"):
                    with ui.column().classes("gap-0"):
                        ui.label(invitation.email).classes("text-sm")
                        ui.label(
                            t(
                                "household.expires",
                                when=invitation.expires_at.strftime("%Y-%m-%d %H:%M"),
                            )
                        ).classes("text-xs text-slate-500")
                    ui.button(
                        t("household.cancel_invitation"),
                        on_click=lambda i=invitation: _cancel(i, refresh),
                    ).props("flat no-caps")


async def _show_link(invitation: Invitation) -> None:
    link = invitation.link(_base_url())
    with ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-lg gap-3"):
        ui.label(t("household.link_title", email=invitation.email)).classes("text-lg font-semibold")
        ui.label(t("household.link_hint")).classes("text-sm text-slate-500")
        ui.label(link).classes(
            "font-mono text-xs select-all p-3 rounded border border-slate-300 w-full break-all"
        ).props('data-testid="invite-link"')
        with ui.row().classes("gap-2 justify-end w-full"):
            ui.button(
                t("unlock.recovery_copy"),
                icon="content_copy",
                on_click=lambda: ui.clipboard.write(link),
            ).props("outline no-caps")
            ui.button(t("common.close"), on_click=lambda: dialog.submit(True)).props(
                "color=primary"
            )
    await dialog
    dialog.delete()


async def _cancel(invitation: PendingInvitation, refresh: Refresh) -> None:
    async def _go(service: HouseholdService) -> None:
        await service.cancel_invitation(invitation.email)

    try:
        await with_household(_go)
    except KaletaError as exc:
        notify_kaleta_error(exc)
        return
    refresh()
