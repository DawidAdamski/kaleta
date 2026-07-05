# SPDX-License-Identifier: AGPL-3.0-or-later
"""Subscription add/edit/delete and detector confirm dialogs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.subscription import DetectorCandidate, SubscriptionResponse, SubscriptionUpdate
from kaleta.services import SubscriptionService, with_session
from kaleta.services.subscription_service import SubscriptionFormError, parse_subscription_form
from kaleta.views.theme import BODY_MUTED


def build_subscription_dialogs(
    *,
    category_opts: dict[int, str],
    sub_category_opts: dict[int, str],
    detector_days: int | None,
) -> tuple[
    Callable[[], None],
    Callable[[SubscriptionResponse], None],
    Callable[[SubscriptionResponse], None],
    Callable[[DetectorCandidate], None],
    Callable[[DetectorCandidate], Awaitable[None]],
    Callable[[int], Awaitable[None]],
    Callable[[int], Awaitable[None]],
    Callable[[int], Awaitable[None]],
]:
    editing_state: dict[str, int | None] = {"id": None}
    pending_delete: dict[str, Any] = {"id": 0, "name": ""}
    pending_candidate: dict[str, DetectorCandidate | None] = {"cand": None}

    with ui.dialog() as fund_dialog, ui.card().classes("w-[520px] gap-3"):
        dialog_title = ui.label(t("subscriptions.dialog_title_new")).classes("text-lg font-bold")
        name_in = (
            ui.input(label=t("subscriptions.field_name")).props("dense outlined").classes("w-full")
        )
        with ui.row().classes("w-full gap-2"):
            amount_in = (
                ui.number(
                    label=t("subscriptions.field_amount"),
                    value=0,
                    min=0,
                    format="%.2f",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
            cadence_in = (
                ui.number(
                    label=t("subscriptions.field_cadence"),
                    value=30,
                    min=1,
                    max=400,
                    format="%d",
                )
                .props("dense outlined")
                .classes("flex-1")
            )
        ui.label(t("subscriptions.field_cadence_hint")).classes(BODY_MUTED)
        with ui.row().classes("w-full gap-2"):
            first_seen_in = (
                ui.input(label=t("subscriptions.field_first_seen"))
                .props("dense outlined type=date")
                .classes("flex-1")
            )
            next_expected_in = (
                ui.input(label=t("subscriptions.field_next_expected"))
                .props("dense outlined type=date")
                .classes("flex-1")
            )
        if category_opts:
            category_in = (
                ui.select(
                    options=category_opts,
                    label=t("subscriptions.field_category"),
                    with_input=True,
                )
                .props("dense outlined clearable")
                .classes("w-full")
            )
        else:
            category_in = None
        url_in = (
            ui.input(label=t("subscriptions.field_url")).props("dense outlined").classes("w-full")
        )
        notes_in = (
            ui.textarea(label=t("subscriptions.field_notes"))
            .props("dense outlined rows=3 autogrow")
            .classes("w-full")
        )
        auto_renew_cb = ui.checkbox(t("subscriptions.field_auto_renew"), value=True)

        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=fund_dialog.close).props("flat")
            save_btn = ui.button(t("common.save"), icon="check").props("color=primary unelevated")

    with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
        ui.label(t("subscriptions.confirm_delete_title")).classes("text-lg font-bold")
        delete_body = ui.label("").classes(BODY_MUTED)
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
            confirm_delete_btn = ui.button(
                t("subscriptions.confirm_delete_confirm"), icon="delete"
            ).props("color=negative unelevated")

    with ui.dialog() as confirm_dialog, ui.card().classes("w-[480px] gap-3"):
        ui.label(t("subscriptions.confirm_title")).classes("text-lg font-bold")
        confirm_body = ui.label("").classes(BODY_MUTED)
        default_sub_cat = next(iter(sub_category_opts)) if sub_category_opts else None
        sub_cat_select = (
            ui.select(
                options=sub_category_opts,
                label=t("subscriptions.confirm_sub_category"),
                value=default_sub_cat,
            )
            .props("dense outlined")
            .classes("w-full")
        )
        ui.label(t("subscriptions.confirm_hint")).classes(BODY_MUTED)
        with ui.row().classes("w-full justify-end gap-2 mt-2"):
            ui.button(t("common.cancel"), on_click=confirm_dialog.close).props("flat")
            confirm_track_btn = ui.button(t("subscriptions.detector_confirm"), icon="check").props(
                "color=primary unelevated"
            )

    def open_add_dialog() -> None:
        editing_state["id"] = None
        dialog_title.set_text(t("subscriptions.dialog_title_new"))
        name_in.set_value("")
        amount_in.set_value(0)
        cadence_in.set_value(30)
        first_seen_in.set_value("")
        next_expected_in.set_value("")
        if category_in is not None:
            category_in.set_value(None)
        url_in.set_value("")
        notes_in.set_value("")
        auto_renew_cb.set_value(True)
        fund_dialog.open()

    def open_edit_dialog(sub: SubscriptionResponse) -> None:
        editing_state["id"] = sub.id
        dialog_title.set_text(t("subscriptions.dialog_title_edit"))
        name_in.set_value(sub.name)
        amount_in.set_value(float(sub.amount))
        cadence_in.set_value(sub.cadence_days)
        first_seen_in.set_value(sub.first_seen_at.isoformat() if sub.first_seen_at else "")
        next_expected_in.set_value(sub.next_expected_at.isoformat() if sub.next_expected_at else "")
        if category_in is not None:
            category_in.set_value(sub.category_id)
        url_in.set_value(sub.url or "")
        notes_in.set_value(sub.notes or "")
        auto_renew_cb.set_value(sub.auto_renew)
        fund_dialog.open()

    async def save_sub() -> None:
        try:
            payload = parse_subscription_form(
                name=name_in.value or "",
                amount_value=amount_in.value,
                cadence_value=cadence_in.value,
                first_seen_value=first_seen_in.value or "",
                next_expected_value=next_expected_in.value or "",
                category_id_value=category_in.value if category_in is not None else None,
                url_value=url_in.value or "",
                notes_value=notes_in.value or "",
                auto_renew=bool(auto_renew_cb.value),
            )
        except SubscriptionFormError as exc:
            ui.notify(exc.message, type="warning")
            return

        async def _persist(session: Any) -> None:
            sub_svc = SubscriptionService(session)
            if editing_state["id"] is None:
                await sub_svc.create(payload)
            else:
                await sub_svc.update(
                    editing_state["id"],
                    SubscriptionUpdate(**payload.model_dump()),
                )

        await with_session(_persist)
        fund_dialog.close()
        ui.notify(t("subscriptions.saved"), type="positive")
        ui.navigate.reload()

    save_btn.on_click(save_sub)

    def open_delete_dialog(sub: SubscriptionResponse) -> None:
        pending_delete["id"] = sub.id
        pending_delete["name"] = sub.name
        delete_body.set_text(t("subscriptions.confirm_delete_body", name=sub.name))
        delete_dialog.open()

    async def confirm_delete() -> None:
        async def _delete(session: Any) -> None:
            await SubscriptionService(session).delete(int(pending_delete["id"]))

        await with_session(_delete)
        delete_dialog.close()
        ui.notify(t("subscriptions.deleted"), type="positive")
        ui.navigate.reload()

    confirm_delete_btn.on_click(confirm_delete)

    async def do_track() -> None:
        cand = pending_candidate["cand"]
        if cand is None:
            return
        sub_cat_id = int(sub_cat_select.value) if sub_cat_select.value is not None else None

        async def _track(session: Any) -> None:
            await SubscriptionService(session).create_from_candidate(
                cand,
                sub_category_id=sub_cat_id,
                window_days=detector_days,
            )

        await with_session(_track)
        confirm_dialog.close()
        ui.notify(t("subscriptions.tracked", name=cand.payee_name), type="positive")
        ui.navigate.reload()

    confirm_track_btn.on_click(do_track)

    async def silent_track_async(cand: DetectorCandidate) -> None:
        async def _track(session: Any) -> None:
            await SubscriptionService(session).create_from_candidate(cand)

        await with_session(_track)
        ui.notify(t("subscriptions.tracked", name=cand.payee_name), type="positive")
        ui.navigate.reload()

    def silent_track(cand: DetectorCandidate) -> None:
        import asyncio

        asyncio.create_task(silent_track_async(cand))

    def confirm_candidate(cand: DetectorCandidate) -> None:
        pending_candidate["cand"] = cand
        confirm_body.set_text(t("subscriptions.confirm_body", name=cand.payee_name))
        if not sub_category_opts:
            silent_track(cand)
            return
        confirm_dialog.open()

    async def dismiss_candidate(cand: DetectorCandidate) -> None:
        async def _dismiss(session: Any) -> None:
            await SubscriptionService(session).dismiss_candidate(cand)

        await with_session(_dismiss)
        ui.notify(t("subscriptions.dismissed_msg"), type="info")
        ui.navigate.reload()

    async def mute(sub_id: int) -> None:
        async def _mute(session: Any) -> None:
            await SubscriptionService(session).mute_one_cycle(sub_id)

        await with_session(_mute)
        ui.notify(t("subscriptions.muted"), type="positive")
        ui.navigate.reload()

    async def cancel(sub_id: int) -> None:
        async def _cancel(session: Any) -> None:
            await SubscriptionService(session).cancel(sub_id)

        await with_session(_cancel)
        ui.notify(t("subscriptions.cancelled"), type="positive")
        ui.navigate.reload()

    async def reactivate(sub_id: int) -> None:
        async def _reactivate(session: Any) -> None:
            await SubscriptionService(session).reactivate(sub_id)

        await with_session(_reactivate)
        ui.notify(t("subscriptions.reactivated"), type="positive")
        ui.navigate.reload()

    return (
        open_add_dialog,
        open_edit_dialog,
        open_delete_dialog,
        confirm_candidate,
        dismiss_candidate,
        mute,
        cancel,
        reactivate,
    )
