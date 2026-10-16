# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from decimal import Decimal
from typing import Any

from nicegui import ui
from pydantic import ValidationError

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.gift import GiftCreate, GiftResponse, GiftsSummary, GiftUpdate
from kaleta.services import GiftService, with_session
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)


def _fmt_amount(d: Decimal) -> str:
    return f"{d:,.2f}"


def register() -> None:
    @ui.page("/wizard/gifts")
    async def gifts_page() -> None:
        async def _load(session: Any) -> GiftsSummary:
            return await GiftService(session).summary()

        summary = await with_session(_load)

        with page_layout(t("gifts.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("gifts.title")).classes(PAGE_TITLE)
                    ui.label(t("gifts.subtitle")).classes(BODY_MUTED)
                with ui.row().classes("items-center gap-4"):
                    with ui.column().classes("gap-0 items-end"):
                        ui.label(t("gifts.yearly_total")).classes(f"{BODY_MUTED} text-xs")
                        ui.label(_fmt_amount(summary.yearly_total)).classes("text-lg font-bold")
                    add_btn = ui.button(t("gifts.add"), icon="add").props(
                        "color=primary unelevated size=md"
                    )

            # ── Add/Edit dialog ──────────────────────────────────────────
            editing_state: dict[str, int | None] = {"id": None}

            with ui.dialog() as gift_dialog, ui.card().classes("w-[460px] gap-3"):
                dialog_title = ui.label(t("gifts.dialog_title")).classes("text-lg font-bold")
                person_in = (
                    ui.input(label=t("gifts.person"))
                    .props("dense outlined maxlength=100")
                    .classes("w-full")
                )
                occasion_in = (
                    ui.input(label=t("gifts.occasion"))
                    .props("dense outlined maxlength=100")
                    .classes("w-full")
                )
                amount_in = (
                    ui.number(label=t("gifts.amount"), value=0, min=0, format="%.2f")
                    .props("dense outlined")
                    .classes("w-full")
                )
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=gift_dialog.close).props("flat")
                    save_btn = ui.button(t("common.save"), icon="check").props(
                        "color=primary unelevated"
                    )

            async def _save_gift() -> None:
                person = (person_in.value or "").strip()
                occasion = (occasion_in.value or "").strip()
                if not person or not occasion or not amount_in.value:
                    ui.notify(t("gifts.incomplete"), type="warning")
                    return
                # Quantize to the stored scale; the schema's decimal_places=2
                # would otherwise reject a float that prints more digits.
                amount = Decimal(str(amount_in.value)).quantize(Decimal("0.01"))
                gift_id = editing_state["id"]
                try:
                    draft = GiftCreate(person=person, occasion=occasion, amount=amount)
                except ValidationError:
                    ui.notify(t("gifts.incomplete"), type="warning")
                    return

                async def _save(session: Any) -> None:
                    svc = GiftService(session)
                    if gift_id is None:
                        await svc.create(draft)
                    else:
                        await svc.update(
                            gift_id,
                            GiftUpdate(
                                person=draft.person,
                                occasion=draft.occasion,
                                amount=draft.amount,
                            ),
                        )

                try:
                    await with_session(_save)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                gift_dialog.close()
                ui.notify(t("gifts.saved"), type="positive")
                ui.navigate.reload()

            save_btn.on_click(_save_gift)

            def _open_add_dialog() -> None:
                editing_state["id"] = None
                dialog_title.set_text(t("gifts.dialog_title"))
                person_in.set_value("")
                occasion_in.set_value("")
                amount_in.set_value(0)
                gift_dialog.open()

            add_btn.on_click(_open_add_dialog)

            def _open_edit_dialog(gift: GiftResponse) -> None:
                editing_state["id"] = gift.id
                dialog_title.set_text(t("gifts.dialog_edit_title"))
                person_in.set_value(gift.person)
                occasion_in.set_value(gift.occasion)
                amount_in.set_value(float(gift.amount))
                gift_dialog.open()

            # ── Delete confirmation dialog ───────────────────────────────
            pending_delete: dict[str, int] = {"id": 0}

            with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
                ui.label(t("gifts.confirm_delete_title")).classes("text-lg font-bold")
                delete_body = ui.label("").classes(BODY_MUTED)
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=delete_dialog.close).props("flat")
                    confirm_delete_btn = ui.button(
                        t("gifts.confirm_delete_confirm"), icon="delete"
                    ).props("color=negative unelevated")

            async def _confirm_delete() -> None:
                gift_id = int(pending_delete["id"])

                async def _delete(session: Any) -> None:
                    await GiftService(session).delete(gift_id)

                try:
                    await with_session(_delete)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                delete_dialog.close()
                ui.notify(t("gifts.deleted"), type="positive")
                ui.navigate.reload()

            confirm_delete_btn.on_click(_confirm_delete)

            def _open_delete_dialog(gift: GiftResponse) -> None:
                pending_delete["id"] = gift.id
                delete_body.set_text(
                    t("gifts.confirm_delete_body", occasion=gift.occasion, person=gift.person)
                )
                delete_dialog.open()

            # ── Gift list, grouped by person ─────────────────────────────
            if not summary.groups:
                ui.label(t("gifts.empty")).classes(f"{BODY_MUTED} mt-4")
                return

            with ui.column().classes("w-full gap-3 mt-2"):
                for group in summary.groups:
                    with ui.card().classes(f"{SECTION_CARD} w-full gap-2"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label(group.person).classes(SECTION_HEADING)
                            ui.label(_fmt_amount(group.subtotal)).classes("font-bold")
                        for gift in group.gifts:
                            with ui.row().classes("w-full items-center justify-between gap-2"):
                                ui.label(gift.occasion).classes("flex-1")
                                ui.label(_fmt_amount(gift.amount)).classes("tabular-nums")
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _e, g=gift: _open_edit_dialog(g),
                                ).props("flat dense round size=sm")
                                ui.button(
                                    icon="delete",
                                    on_click=lambda _e, g=gift: _open_delete_dialog(g),
                                ).props("flat dense round size=sm color=negative")
