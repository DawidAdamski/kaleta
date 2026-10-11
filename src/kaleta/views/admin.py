# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/admin``: the instance administrator's page (ADR-38 §5, ``instance-admin-panel``).

Families, registration, logins and the audit trail — e-mail addresses, counts
and statuses, never a family's data. Everything goes through
``InstanceAdminService`` via ``kaleta.auth.admin``, which asks the registry on
every call: anyone who is not an administrator gets a 404, not a disabled page.

Every action first proves the administrator's password (and code, with
two-factor sign-in on) unless that was done in the last fifteen minutes.
A password the page makes for someone else is shown once, in a dialog.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi.responses import Response
from nicegui import ui

from kaleta.auth.admin import (
    ADMIN_PATH,
    admin_needs_code,
    admin_step_up_needed,
    prove_admin,
    set_login_disabled_as_admin,
    with_admin_service,
)
from kaleta.exceptions import KaletaError, NotFoundError
from kaleta.i18n import t
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.instance_admin_service import (
    FamilyRow,
    InstanceAdminService,
    InstanceInfo,
    LoginRow,
    OneTimePassword,
)
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    BODY_MUTED,
    DIALOG_TITLE,
    MONO,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

_STATUS_CHIP = "k-cell-chip"
_ROW = "w-full items-center gap-3 py-2 border-b k-hairline"


@dataclass(frozen=True)
class _AuditLine:
    at: datetime
    action: str
    actor: str
    target: str


@dataclass(frozen=True)
class _Snapshot:
    info: InstanceInfo
    families: list[FamilyRow]
    logins: list[LoginRow]
    audit: list[_AuditLine]


async def _load(service: InstanceAdminService) -> _Snapshot:
    info = await service.info()
    logins = await service.logins() if info.auth_backend == "local" else []
    email_of = {f"local:{row.identity_id}": row.email for row in logins}
    audit = [
        _AuditLine(
            at=entry.at,
            action=entry.action.value,
            actor=email_of.get(entry.actor or "", entry.actor or "kaleta-admin"),
            target=_target(entry.tenant_id, entry.identity_id, _detail(entry.detail)),
        )
        for entry in await service.audit_trail()
    ]
    return _Snapshot(info=info, families=await service.families(), logins=logins, audit=audit)


def _target(tenant_id: int | None, identity_id: int | None, detail: str | None) -> str:
    parts = []
    if tenant_id is not None:
        parts.append(t("admin.audit_family", id=tenant_id))
    if identity_id is not None:
        parts.append(t("admin.audit_login", id=identity_id))
    if detail:
        parts.append(detail)
    return " · ".join(parts)


def _detail(detail: str | None) -> str | None:
    """The only detail written is a registration mode: say it in the page's language."""
    modes = {m.value for m in RegistrationMode}
    return t(f"admin.registration_{detail}") if detail in modes else detail


def _when(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M") if moment is not None else "—"


def register() -> None:
    @ui.page(ADMIN_PATH)
    async def admin_page() -> Response | None:
        try:
            snapshot = await with_admin_service(_load)
        except NotFoundError:
            return Response("Not Found", status_code=404, media_type="text/plain")
        with page_layout(t("admin.title")):
            ui.label(t("admin.title")).classes(PAGE_TITLE)
            ui.label(t("admin.subtitle")).classes(f"{BODY_MUTED} mb-2")
            _AdminPage().render(snapshot)
        return None


class _AdminPage:
    """The page's sections, redrawn together after every action."""

    def render(self, snapshot: _Snapshot) -> None:
        # Dialogs live here: a button's own slot is gone once the redraw after
        # its action has cleared the body it sat in.
        self._anchor = ui.element("div")
        self._body = ui.column().classes("w-full gap-4")
        self._draw(snapshot)

    async def _refresh(self) -> None:
        try:
            snapshot = await with_admin_service(_load)
        except NotFoundError:
            # No longer an administrator (demoted elsewhere): nothing to show.
            ui.navigate.to("/")
            return
        self._draw(snapshot)

    def _draw(self, snapshot: _Snapshot) -> None:
        """Every section, from one snapshot of the registry."""
        self._body.clear()
        with self._body:
            self._instance(snapshot.info)
            if snapshot.info.registration is not None:
                self._registration(snapshot.info.registration)
            self._families(snapshot)
            self._logins(snapshot)
            self._audit(snapshot.audit)

    # ── Running an action ────────────────────────────────────────────────────

    async def _act(
        self, action: Callable[[InstanceAdminService], Awaitable[Any]], *, done: str
    ) -> Any:
        """Step up if due, run ``action``, say so, redraw. ``None`` when it did not run."""
        if admin_step_up_needed() and not await self._step_up():
            return None
        try:
            result = await with_admin_service(action)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return None
        ui.notify(t(done), type="positive")
        await self._refresh()
        return result if result is not None else True

    # ── Sections ─────────────────────────────────────────────────────────────

    def _instance(self, info: InstanceInfo) -> None:
        with ui.card().classes(SECTION_CARD).props('data-testid="admin-instance"'):
            ui.label(t("admin.instance_title")).classes(SECTION_HEADING)
            with ui.grid(columns=2).classes("gap-x-8 gap-y-1 mt-2"):
                facts = [
                    ("admin.version", info.version),
                    ("admin.backend", info.auth_backend),
                    ("admin.family_count", str(info.families)),
                ]
                if info.logins is not None:
                    facts.append(("admin.login_count", str(info.logins)))
                for key, value in facts:
                    ui.label(t(key)).classes(BODY_MUTED)
                    ui.label(value).classes(MONO)

    def _registration(self, mode: RegistrationMode) -> None:
        with ui.card().classes(SECTION_CARD).props('data-testid="admin-registration"'):
            ui.label(t("admin.registration_title")).classes(SECTION_HEADING)
            options = {m.value: t(f"admin.registration_{m.value}") for m in RegistrationMode}
            radio = ui.radio(options, value=mode.value).props("inline")
            ui.label(t(f"admin.registration_{mode.value}_hint")).classes(f"{BODY_MUTED} mt-1")
            if mode is RegistrationMode.OPEN:
                ui.label(t("admin.registration_open_warning")).classes("text-sm text-warning")

            async def _change(event: Any) -> None:
                chosen = RegistrationMode(event.value)
                if chosen is mode:
                    return

                async def _set(service: InstanceAdminService) -> None:
                    await service.set_registration_mode(chosen)

                if await self._act(_set, done="admin.registration_saved") is None:
                    radio.set_value(mode.value)

            radio.on_value_change(_change)

    def _families(self, snapshot: _Snapshot) -> None:
        local = snapshot.info.auth_backend == "local"
        with ui.card().classes(SECTION_CARD).props('data-testid="admin-families"'):
            with ui.row().classes("w-full items-center"):
                ui.label(t("admin.families_title")).classes(f"{SECTION_HEADING} flex-1")
                if local:
                    ui.button(
                        t("admin.family_new"), icon="add", on_click=self._create_family
                    ).props("unelevated no-caps color=primary")
            if not snapshot.families:
                ui.label(t("admin.families_empty")).classes(BODY_MUTED)
            for family in snapshot.families:
                self._family_row(family)

    def _family_row(self, family: FamilyRow) -> None:
        pending = family.owner_signed_in is False and family.status.value == "active"
        status = "pending" if pending else family.status.value
        with ui.row().classes(_ROW).props(f'data-testid="admin-family-{family.tenant_id}"'):
            with ui.column().classes("flex-1 min-w-0 gap-0"):
                ui.label(family.name or family.owner_email or f"#{family.tenant_id}").classes(
                    "font-medium"
                )
                ui.label(
                    t(
                        "admin.family_line",
                        owner=family.owner_email or "—",
                        members=family.members,
                        created=_when(family.created_at),
                    )
                ).classes(BODY_MUTED)
            ui.label(t(f"admin.status_{status}")).classes(_STATUS_CHIP).props(
                'data-testid="admin-family-status"'
            )
            if family.status.value == "suspended":
                ui.button(
                    t("admin.resume"), on_click=lambda f=family: self._resume(f.tenant_id)
                ).props("flat no-caps")
            elif family.status.value == "active":
                ui.button(
                    t("admin.suspend"), on_click=lambda f=family: self._suspend(f.tenant_id)
                ).props("flat no-caps")
            ui.button(t("admin.delete"), on_click=lambda f=family: self._delete(f)).props(
                "flat no-caps color=negative"
            )

    def _logins(self, snapshot: _Snapshot) -> None:
        with ui.card().classes(SECTION_CARD).props('data-testid="admin-logins"'):
            ui.label(t("admin.logins_title")).classes(SECTION_HEADING)
            if snapshot.info.auth_backend != "local":
                ui.label(t("admin.logins_supabase")).classes(BODY_MUTED)
                return
            for login in snapshot.logins:
                self._login_row(login)

    def _login_row(self, login: LoginRow) -> None:
        with ui.row().classes(_ROW).props(f'data-testid="admin-login-{login.identity_id}"'):
            with ui.column().classes("flex-1 min-w-0 gap-0"):
                ui.label(login.email).classes("font-medium")
                marks = [
                    t(key)
                    for key, on in (
                        ("admin.mark_admin", login.is_admin),
                        ("admin.mark_disabled", login.disabled),
                        ("admin.mark_must_change", login.must_change_password),
                    )
                    if on
                ]
                ui.label(
                    " · ".join([*marks, t("admin.last_login", at=_when(login.last_login_at))])
                ).classes(BODY_MUTED)
            with (
                ui.button(icon="more_vert").props(
                    f'flat round aria-label="{t("admin.login_actions")}"'
                ),
                ui.menu(),
            ):
                ui.menu_item(t("admin.reset_password"), on_click=lambda r=login: self._reset(r))
                ui.menu_item(t("admin.revoke_sessions"), on_click=lambda r=login: self._revoke(r))
                ui.menu_item(
                    t("admin.enable" if login.disabled else "admin.disable"),
                    on_click=lambda r=login: self._toggle_disabled(r),
                )
                ui.menu_item(
                    t("admin.demote" if login.is_admin else "admin.promote"),
                    on_click=lambda r=login: self._toggle_admin(r),
                )

    def _audit(self, lines: list[_AuditLine]) -> None:
        with ui.card().classes(SECTION_CARD).props('data-testid="admin-audit"'):
            ui.label(t("admin.audit_title")).classes(SECTION_HEADING)
            if not lines:
                ui.label(t("admin.audit_empty")).classes(BODY_MUTED)
            for line in lines:
                with ui.row().classes("w-full gap-3 text-sm py-1"):
                    ui.label(_when(line.at)).classes(f"{MONO} {BODY_MUTED}")
                    ui.label(t(f"admin.action_{line.action}")).classes("font-medium")
                    ui.label(line.target).classes(BODY_MUTED)
                    ui.label(line.actor).classes(f"{BODY_MUTED} ml-auto")

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _create_family(self) -> None:
        with self._anchor, ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3"):
            ui.label(t("admin.family_new")).classes(DIALOG_TITLE)
            name = ui.input(t("admin.family_name")).classes("w-full")
            email = ui.input(t("admin.owner_email")).classes("w-full")
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button(t("common.cancel"), on_click=lambda: dialog.submit(None)).props("flat")
                ui.button(
                    t("admin.family_create"),
                    on_click=lambda: dialog.submit((name.value or "", email.value or "")),
                ).props("unelevated color=primary")
        answer = await dialog
        dialog.delete()
        if not answer:
            return
        family_name, owner = answer

        async def _create(service: InstanceAdminService) -> OneTimePassword:
            return (await service.create_family(owner, family_name)).owner

        created = await self._act(_create, done="admin.family_created")
        if isinstance(created, OneTimePassword):
            await self._show_password(created, "admin.family_created_hint")

    async def _suspend(self, tenant_id: int) -> None:
        async def _do(service: InstanceAdminService) -> None:
            await service.suspend(tenant_id)

        await self._act(_do, done="admin.suspended")

    async def _resume(self, tenant_id: int) -> None:
        async def _do(service: InstanceAdminService) -> None:
            await service.resume(tenant_id)

        await self._act(_do, done="admin.resumed")

    async def _delete(self, family: FamilyRow) -> None:
        with self._anchor, ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-md gap-3"):
            ui.label(t("admin.delete_title")).classes(DIALOG_TITLE)
            ui.label(t("admin.delete_body", label=family.label)).classes("text-sm text-negative")
            typed = ui.input(t("admin.delete_type")).classes("w-full")
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button(t("common.cancel"), on_click=lambda: dialog.submit(None)).props("flat")
                ui.button(
                    t("admin.delete_confirm"), on_click=lambda: dialog.submit(typed.value or "")
                ).props("unelevated color=negative")
        answer = await dialog
        dialog.delete()
        if answer is None:
            return

        async def _do(service: InstanceAdminService) -> None:
            await service.delete(family.tenant_id, typed=answer)

        await self._act(_do, done="admin.deleted")

    async def _reset(self, login: LoginRow) -> None:
        async def _do(service: InstanceAdminService) -> OneTimePassword:
            return (await service.reset_password(login.identity_id)).login

        reset = await self._act(_do, done="admin.password_reset")
        if isinstance(reset, OneTimePassword):
            await self._show_password(reset, "admin.password_reset_hint")

    async def _revoke(self, login: LoginRow) -> None:
        async def _do(service: InstanceAdminService) -> None:
            await service.revoke_sessions(login.identity_id)

        await self._act(_do, done="admin.sessions_revoked")

    async def _toggle_disabled(self, login: LoginRow) -> None:
        async def _do(service: InstanceAdminService) -> None:
            await set_login_disabled_as_admin(service, login.identity_id, not login.disabled)

        await self._act(_do, done="admin.enabled" if login.disabled else "admin.disabled")

    async def _toggle_admin(self, login: LoginRow) -> None:
        async def _do(service: InstanceAdminService) -> None:
            await service.set_admin(login.identity_id, not login.is_admin)

        await self._act(_do, done="admin.demoted" if login.is_admin else "admin.promoted")

    async def _step_up(self) -> bool:
        """Ask for the password (and code); ``True`` once it is proved."""
        needs_code = await admin_needs_code()
        with self._anchor, ui.dialog() as dialog, ui.card().classes("p-6 w-full max-w-sm gap-3"):
            ui.label(t("admin.step_up_title")).classes(DIALOG_TITLE)
            ui.label(t("admin.step_up_code_hint" if needs_code else "admin.step_up_hint")).classes(
                BODY_MUTED
            )
            password = ui.input(t("auth.password"), password=True).classes("w-full")
            code = ui.input(t("settings.mfa_code")).classes("w-full")
            code.set_visibility(needs_code)
            error = ui.label("").classes("text-sm text-negative")

            async def _confirm() -> None:
                try:
                    await prove_admin(password.value or "", code.value or "")
                except KaletaError as exc:
                    error.set_text(exc.message)
                    return
                dialog.submit(True)

            password.on("keydown.enter", _confirm)
            code.on("keydown.enter", _confirm)
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button(t("common.cancel"), on_click=lambda: dialog.submit(False)).props("flat")
                ui.button(t("admin.step_up_confirm"), on_click=_confirm).props(
                    "unelevated color=primary"
                )
        result = await dialog
        dialog.delete()
        return bool(result)

    async def _show_password(self, login: OneTimePassword, hint_key: str) -> None:
        """The one time anyone sees this password."""
        with (
            self._anchor,
            ui.dialog().props("persistent") as dialog,
            ui.card().classes("p-6 w-full max-w-md gap-3"),
        ):
            ui.label(t("admin.password_title", email=login.email)).classes(DIALOG_TITLE)
            ui.label(t(hint_key)).classes(BODY_MUTED)
            ui.label(login.password).classes(f"{MONO} text-lg select-all").props(
                'data-testid="admin-one-time-password"'
            )
            with ui.row().classes("gap-2 justify-end w-full"):
                ui.button(t("common.close"), on_click=lambda: dialog.submit(True)).props(
                    "unelevated color=primary"
                )
        await dialog
        dialog.delete()
