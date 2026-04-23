from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import CategoryType
from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.subscription import (
    DetectorCandidate,
    RenewalRow,
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
)
from kaleta.services import CategoryService, SubscriptionService
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    BODY_MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

_STATUS_COLOR: dict[SubscriptionStatus, str] = {
    SubscriptionStatus.ACTIVE: "positive",
    SubscriptionStatus.MUTED: "amber-7",
    SubscriptionStatus.CANCELLED: "grey-6",
}


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def _fmt_date(d: datetime.date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _cadence_label(days: int) -> str:
    if 27 <= days <= 33:
        return t("subscriptions.detector_cadence_monthly")
    if 350 <= days <= 380:
        return t("subscriptions.detector_cadence_yearly")
    return f"{days}d"


def _days_away_label(days: int) -> str:
    if days <= 0:
        return t("subscriptions.renewals_today")
    if days == 1:
        return t("subscriptions.renewals_tomorrow")
    return t("subscriptions.renewals_days_away", days=days)


def register() -> None:
    @ui.page("/wizard/subscriptions")
    async def subscriptions_page() -> None:
        async with AsyncSessionFactory() as session:
            svc = SubscriptionService(session)
            subs = await svc.list()
            totals = await svc.totals()
            detector_days = int(
                app.storage.user.get("subscriptions_detector_days", 0) or 0
            ) or None
            candidates = await svc.detect_candidates(window_days=detector_days)
            renewals = await svc.upcoming_renewals(days=30)
            expense_cats = await CategoryService(session).list(type=CategoryType.EXPENSE)

        sub_responses = [SubscriptionResponse.model_validate(s) for s in subs]
        category_opts: dict[int, str] = {c.id: c.name for c in expense_cats}

        with page_layout(t("subscriptions.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("subscriptions.title")).classes(PAGE_TITLE)
                    ui.label(t("subscriptions.subtitle")).classes(BODY_MUTED)
                with ui.row().classes("items-center gap-3"):
                    ui.badge(
                        t(
                            "subscriptions.active_count",
                            count=totals.active_count,
                        ),
                        color="primary",
                    ).classes("text-sm px-3 py-1")
                    with ui.column().classes("items-end gap-0"):
                        ui.label(
                            t(
                                "subscriptions.total_monthly",
                                amount=_fmt(totals.monthly_total),
                            )
                        ).classes("text-base font-semibold")
                        ui.label(
                            t(
                                "subscriptions.total_yearly",
                                amount=_fmt(totals.yearly_total),
                            )
                        ).classes("text-xs text-slate-500")

            # ── Add/Edit dialog + Delete-confirm (shared) ────────────────
            editing_state: dict[str, int | None] = {"id": None}
            pending_delete: dict[str, Any] = {"id": 0, "name": ""}

            with ui.dialog() as fund_dialog, ui.card().classes("w-[520px] gap-3"):
                dialog_title = ui.label(t("subscriptions.dialog_title_new")).classes(
                    "text-lg font-bold"
                )
                name_in = (
                    ui.input(label=t("subscriptions.field_name"))
                    .props("dense outlined")
                    .classes("w-full")
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
                    ui.input(label=t("subscriptions.field_url"))
                    .props("dense outlined")
                    .classes("w-full")
                )
                notes_in = (
                    ui.textarea(label=t("subscriptions.field_notes"))
                    .props("dense outlined rows=3 autogrow")
                    .classes("w-full")
                )
                auto_renew_cb = ui.checkbox(t("subscriptions.field_auto_renew"), value=True)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=fund_dialog.close).props("flat")
                    save_btn = ui.button(
                        t("common.save"), icon="check"
                    ).props("color=primary unelevated")

            with ui.dialog() as delete_dialog, ui.card().classes("w-[440px] gap-3"):
                ui.label(t("subscriptions.confirm_delete_title")).classes(
                    "text-lg font-bold"
                )
                delete_body = ui.label("").classes(BODY_MUTED)
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=delete_dialog.close).props(
                        "flat"
                    )
                    confirm_delete_btn = ui.button(
                        t("subscriptions.confirm_delete_confirm"), icon="delete"
                    ).props("color=negative unelevated")

            # ── Helpers ──────────────────────────────────────────────────
            def _open_add_dialog() -> None:
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

            def _open_edit_dialog(sub: SubscriptionResponse) -> None:
                editing_state["id"] = sub.id
                dialog_title.set_text(t("subscriptions.dialog_title_edit"))
                name_in.set_value(sub.name)
                amount_in.set_value(float(sub.amount))
                cadence_in.set_value(sub.cadence_days)
                first_seen_in.set_value(
                    sub.first_seen_at.isoformat() if sub.first_seen_at else ""
                )
                next_expected_in.set_value(
                    sub.next_expected_at.isoformat() if sub.next_expected_at else ""
                )
                if category_in is not None:
                    category_in.set_value(sub.category_id)
                url_in.set_value(sub.url or "")
                notes_in.set_value(sub.notes or "")
                auto_renew_cb.set_value(sub.auto_renew)
                fund_dialog.open()

            async def _save_sub() -> None:
                try:
                    name = (name_in.value or "").strip()
                    if not name:
                        ui.notify("Name required", type="warning")
                        return
                    amount = Decimal(str(amount_in.value or 0))
                    if amount <= 0:
                        ui.notify("Amount must be > 0", type="warning")
                        return
                    cadence = int(cadence_in.value or 30)
                    first_seen = (
                        datetime.date.fromisoformat(first_seen_in.value)
                        if first_seen_in.value
                        else None
                    )
                    next_expected = (
                        datetime.date.fromisoformat(next_expected_in.value)
                        if next_expected_in.value
                        else None
                    )
                    url = (url_in.value or "").strip() or None
                    notes = (notes_in.value or "").strip() or None
                    category_id = (
                        int(category_in.value)
                        if category_in is not None and category_in.value
                        else None
                    )
                except (ValueError, TypeError) as exc:
                    ui.notify(str(exc), type="negative")
                    return

                async with AsyncSessionFactory() as s:
                    sub_svc = SubscriptionService(s)
                    if editing_state["id"] is None:
                        await sub_svc.create(
                            SubscriptionCreate(
                                name=name,
                                amount=amount,
                                cadence_days=cadence,
                                first_seen_at=first_seen,
                                next_expected_at=next_expected,
                                category_id=category_id,
                                url=url,
                                auto_renew=bool(auto_renew_cb.value),
                                notes=notes,
                            )
                        )
                    else:
                        await sub_svc.update(
                            editing_state["id"],
                            SubscriptionUpdate(
                                name=name,
                                amount=amount,
                                cadence_days=cadence,
                                first_seen_at=first_seen,
                                next_expected_at=next_expected,
                                category_id=category_id,
                                url=url,
                                auto_renew=bool(auto_renew_cb.value),
                                notes=notes,
                            ),
                        )
                fund_dialog.close()
                ui.notify(t("subscriptions.saved"), type="positive")
                ui.navigate.reload()

            save_btn.on_click(_save_sub)

            def _open_delete_dialog(sub: SubscriptionResponse) -> None:
                pending_delete["id"] = sub.id
                pending_delete["name"] = sub.name
                delete_body.set_text(
                    t("subscriptions.confirm_delete_body", name=sub.name)
                )
                delete_dialog.open()

            async def _confirm_delete() -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).delete(int(pending_delete["id"]))
                delete_dialog.close()
                ui.notify(t("subscriptions.deleted"), type="positive")
                ui.navigate.reload()

            confirm_delete_btn.on_click(_confirm_delete)

            async def _confirm_candidate(cand: DetectorCandidate) -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).create_from_candidate(cand)
                ui.notify(
                    t("subscriptions.tracked", name=cand.payee_name),
                    type="positive",
                )
                ui.navigate.reload()

            async def _dismiss_candidate(cand: DetectorCandidate) -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).dismiss_candidate(cand)
                ui.notify(t("subscriptions.dismissed_msg"), type="info")
                ui.navigate.reload()

            async def _mute(sub_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).mute_one_cycle(sub_id)
                ui.notify(t("subscriptions.muted"), type="positive")
                ui.navigate.reload()

            async def _cancel(sub_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).cancel(sub_id)
                ui.notify(t("subscriptions.cancelled"), type="positive")
                ui.navigate.reload()

            async def _reactivate(sub_id: int) -> None:
                async with AsyncSessionFactory() as s:
                    await SubscriptionService(s).reactivate(sub_id)
                ui.notify(t("subscriptions.reactivated"), type="positive")
                ui.navigate.reload()

            # ── Add button (top-right of header) ─────────────────────────
            with ui.row().classes("w-full justify-end"):
                ui.button(
                    t("subscriptions.add"), icon="add", on_click=_open_add_dialog
                ).props("color=primary unelevated size=sm")

            # ── Detector section ─────────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                ui.label(t("subscriptions.detector_heading")).classes(SECTION_HEADING)
                ui.label(t("subscriptions.detector_hint")).classes(BODY_MUTED)
                if not candidates:
                    ui.label(t("subscriptions.detector_empty")).classes(
                        f"{BODY_MUTED} mt-2"
                    )
                else:
                    for cand in candidates:
                        _render_candidate_row(
                            cand, _confirm_candidate, _dismiss_candidate
                        )

            # ── Renewals section ─────────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                ui.label(t("subscriptions.renewals_heading")).classes(SECTION_HEADING)
                if not renewals:
                    ui.label(t("subscriptions.renewals_empty")).classes(
                        f"{BODY_MUTED} mt-2"
                    )
                else:
                    for r in renewals:
                        _render_renewal_row(r)

            # ── All subscriptions ────────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                ui.label(t("subscriptions.active_heading")).classes(SECTION_HEADING)
                if not sub_responses:
                    ui.label(t("subscriptions.active_empty")).classes(
                        f"{BODY_MUTED} mt-2"
                    )
                else:
                    for sub in sub_responses:
                        _render_sub_row(
                            sub,
                            on_edit=_open_edit_dialog,
                            on_mute=_mute,
                            on_cancel=_cancel,
                            on_reactivate=_reactivate,
                            on_delete=_open_delete_dialog,
                        )


def _render_candidate_row(
    cand: DetectorCandidate, on_confirm: Any, on_dismiss: Any
) -> None:
    with ui.row().classes("w-full items-center gap-3 py-2"):
        ui.icon("autorenew", size="1.3rem").classes("text-primary")
        with ui.column().classes("flex-1 gap-0"):
            ui.label(cand.payee_name).classes("text-sm font-medium")
            ui.label(
                t(
                    "subscriptions.detector_occurrences",
                    count=cand.occurrences,
                    date=_fmt_date(cand.last_seen_at),
                )
            ).classes("text-xs text-slate-500")
        ui.label(_cadence_label(cand.cadence_days)).classes(
            "text-xs text-slate-500 w-20 text-right"
        )
        ui.label(_fmt(cand.amount)).classes(f"{AMOUNT_EXPENSE} w-24 text-right text-sm")
        ui.button(
            t("subscriptions.detector_confirm"),
            icon="check",
            on_click=lambda _e, c=cand: on_confirm(c),
        ).props("color=primary unelevated size=sm")
        ui.button(
            icon="close",
            on_click=lambda _e, c=cand: on_dismiss(c),
        ).props("flat dense round color=grey-7").tooltip(
            t("subscriptions.detector_dismiss")
        )


def _render_renewal_row(r: RenewalRow) -> None:
    with ui.row().classes("w-full items-center gap-3 py-1"):
        ui.label(_fmt_date(r.expected_at)).classes("w-24 text-xs text-slate-500")
        ui.label(r.name).classes("flex-1 text-sm")
        ui.label(_days_away_label(r.days_away)).classes(
            "text-xs text-slate-500 w-28 text-right"
        )
        ui.label(_fmt(r.amount)).classes(f"{AMOUNT_EXPENSE} w-24 text-right text-sm")


def _render_sub_row(
    sub: SubscriptionResponse,
    *,
    on_edit: Any,
    on_mute: Any,
    on_cancel: Any,
    on_reactivate: Any,
    on_delete: Any,
) -> None:
    colour = _STATUS_COLOR[sub.status]
    is_active = sub.status == SubscriptionStatus.ACTIVE
    is_cancelled = sub.status == SubscriptionStatus.CANCELLED

    row_classes = "w-full items-center gap-3 py-2"
    if not is_active:
        row_classes += " opacity-75"

    with ui.row().classes(row_classes):
        ui.icon("subscriptions", size="1.3rem").classes(f"text-{colour}")
        with ui.column().classes("flex-1 gap-0"):
            ui.label(sub.name).classes("text-sm font-medium")
            _sub_row_subtitle(sub)
            _sub_row_notes(sub)
        ui.chip(t(f"subscriptions.status_{sub.status.value}"), color=colour).props(
            "dense outline"
        )
        ui.label(_fmt(sub.amount)).classes(f"{AMOUNT_EXPENSE} w-24 text-right text-sm")
        # Actions
        ui.button(icon="edit", on_click=lambda _e, s=sub: on_edit(s)).props(
            "flat dense round color=grey-7"
        ).tooltip(t("subscriptions.action_edit"))
        if is_active:
            ui.button(
                icon="volume_off",
                on_click=lambda _e, sid=sub.id: on_mute(sid),
            ).props("flat dense round color=grey-7").tooltip(
                t("subscriptions.action_mute")
            )
            ui.button(
                icon="cancel",
                on_click=lambda _e, sid=sub.id: on_cancel(sid),
            ).props("flat dense round color=amber-7").tooltip(
                t("subscriptions.action_cancel")
            )
        elif is_cancelled or sub.status == SubscriptionStatus.MUTED:
            ui.button(
                icon="refresh",
                on_click=lambda _e, sid=sub.id: on_reactivate(sid),
            ).props("flat dense round color=primary").tooltip(
                t("subscriptions.action_reactivate")
            )
        ui.button(
            icon="delete",
            on_click=lambda _e, s=sub: on_delete(s),
        ).props("flat dense round color=negative").tooltip(
            t("subscriptions.action_delete")
        )


def _sub_row_subtitle(sub: SubscriptionResponse) -> None:
    parts: list[str] = [_cadence_label(sub.cadence_days)]
    if sub.status == SubscriptionStatus.MUTED and sub.muted_until:
        parts.append(t("subscriptions.muted_until", date=_fmt_date(sub.muted_until)))
    elif sub.status == SubscriptionStatus.CANCELLED and sub.cancelled_at:
        parts.append(
            t("subscriptions.cancelled_on", date=_fmt_date(sub.cancelled_at))
        )
    elif sub.next_expected_at:
        parts.append(_fmt_date(sub.next_expected_at))
    ui.label(" · ".join(parts)).classes("text-xs text-slate-500")


_NOTE_PREVIEW_CHARS = 80


def _sub_row_notes(sub: SubscriptionResponse) -> None:
    """Inline note block under the subtitle — collapsed preview expands on click."""
    if not sub.notes:
        return
    notes = sub.notes
    # Collapse multi-line notes into a single line for the preview view only.
    preview_source = notes.replace("\n", " ").strip()
    is_truncated = len(preview_source) > _NOTE_PREVIEW_CHARS
    preview_text = (
        preview_source[:_NOTE_PREVIEW_CHARS].rstrip() + "…"
        if is_truncated
        else preview_source
    )
    can_toggle = is_truncated or "\n" in notes

    preview_row = ui.row().classes(
        "items-center gap-1 mt-0.5" + (" cursor-pointer" if can_toggle else "")
    )
    with preview_row:
        ui.icon("sticky_note_2", size="0.9rem").classes("text-slate-500")
        ui.label(preview_text).classes("text-xs text-slate-500")

    full_row = ui.row().classes("items-start gap-1 mt-0.5 cursor-pointer")
    full_row.set_visibility(False)
    with full_row:
        ui.icon("sticky_note_2", size="0.9rem").classes("text-slate-500 mt-0.5")
        ui.label(notes).classes(
            "text-xs text-slate-500 whitespace-pre-line leading-snug"
        )

    if can_toggle:
        def _toggle(_e: object = None) -> None:
            preview_row.set_visibility(not preview_row.visible)
            full_row.set_visibility(not full_row.visible)

        preview_row.on("click", _toggle)
        full_row.on("click", _toggle)
