"""Subscription list row renderers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.subscription import DetectorCandidate, RenewalRow, SubscriptionResponse
from kaleta.services.subscription_service import (
    SubscriptionCategoryGroup,
    build_notes_preview,
    category_group_monthly_total,
)
from kaleta.views.components.amount_label import amount_css_class
from kaleta.views.subscriptions.constants import STATUS_COLOR
from kaleta.views.subscriptions.helpers import cadence_label, days_away_label, fmt_amount, fmt_date


def render_category_group(group: SubscriptionCategoryGroup) -> None:
    """One collapsible block per Subscriptions-tree child category."""
    monthly_total = category_group_monthly_total(group)
    heading = t(
        "subscriptions.by_category_group",
        name=group.category_name,
        total=f"{monthly_total:,.2f}",
    )
    expense_cls = amount_css_class("expense")
    with ui.expansion(heading, icon="subscriptions").classes("w-full").props("dense"):
        for row in group.merchants:
            with ui.row().classes("w-full items-center gap-3 py-1"):
                ui.label(row.label).classes("flex-1 text-sm")
                ui.label(t("subscriptions.by_category_charges", count=row.charges)).classes(
                    "text-xs text-slate-500 w-28 text-right"
                )
                ui.label(f"{row.total_spent:,.2f}").classes(
                    f"{expense_cls} w-28 text-right text-sm"
                )


def render_candidate_row(
    cand: DetectorCandidate,
    on_confirm: Callable[[DetectorCandidate], None],
    on_dismiss: Callable[[DetectorCandidate], Awaitable[None]],
) -> None:
    expense_cls = amount_css_class("expense")
    with ui.row().classes("w-full items-center gap-3 py-2"):
        ui.icon("autorenew", size="1.3rem").classes("text-primary")
        with ui.column().classes("flex-1 gap-0"):
            ui.label(cand.payee_name).classes("text-sm font-medium")
            ui.label(
                t(
                    "subscriptions.detector_occurrences",
                    count=cand.occurrences,
                    date=fmt_date(cand.last_seen_at),
                )
            ).classes("text-xs text-slate-500")
        ui.label(cadence_label(cand.cadence_days)).classes("text-xs text-slate-500 w-20 text-right")
        ui.label(fmt_amount(cand.amount)).classes(f"{expense_cls} w-24 text-right text-sm")
        ui.button(
            t("subscriptions.detector_confirm"),
            icon="check",
            on_click=lambda _e, c=cand: on_confirm(c),
        ).props("color=primary unelevated size=sm")
        ui.button(
            icon="close",
            on_click=lambda _e, c=cand: on_dismiss(c),
        ).props("flat dense round color=grey-7").tooltip(t("subscriptions.detector_dismiss"))


def render_renewal_row(row: RenewalRow) -> None:
    expense_cls = amount_css_class("expense")
    with ui.row().classes("w-full items-center gap-3 py-1"):
        ui.label(fmt_date(row.expected_at)).classes("w-24 text-xs text-slate-500")
        ui.label(row.name).classes("flex-1 text-sm")
        ui.label(days_away_label(row.days_away)).classes("text-xs text-slate-500 w-28 text-right")
        ui.label(fmt_amount(row.amount)).classes(f"{expense_cls} w-24 text-right text-sm")


def render_sub_row(
    sub: SubscriptionResponse,
    *,
    on_edit: Callable[[SubscriptionResponse], None],
    on_mute: Callable[[int], Awaitable[None]],
    on_cancel: Callable[[int], Awaitable[None]],
    on_reactivate: Callable[[int], Awaitable[None]],
    on_delete: Callable[[SubscriptionResponse], None],
) -> None:
    colour = STATUS_COLOR[sub.status.value]
    is_active = sub.status.value == "active"
    is_cancelled = sub.status.value == "cancelled"
    expense_cls = amount_css_class("expense")

    row_classes = "w-full items-center gap-3 py-2"
    if not is_active:
        row_classes += " opacity-75"

    with ui.row().classes(row_classes):
        ui.icon("subscriptions", size="1.3rem").classes(f"text-{colour}")
        with ui.column().classes("flex-1 gap-0"):
            ui.label(sub.name).classes("text-sm font-medium")
            _render_sub_row_subtitle(sub)
            _render_sub_row_notes(sub)
        ui.chip(t(f"subscriptions.status_{sub.status.value}"), color=colour).props("dense outline")
        ui.label(fmt_amount(sub.amount)).classes(f"{expense_cls} w-24 text-right text-sm")
        ui.button(icon="edit", on_click=lambda _e, s=sub: on_edit(s)).props(
            "flat dense round color=grey-7"
        ).tooltip(t("subscriptions.action_edit"))
        if is_active:
            ui.button(
                icon="volume_off",
                on_click=lambda _e, sid=sub.id: on_mute(sid),
            ).props("flat dense round color=grey-7").tooltip(t("subscriptions.action_mute"))
            ui.button(
                icon="cancel",
                on_click=lambda _e, sid=sub.id: on_cancel(sid),
            ).props("flat dense round color=amber-7").tooltip(t("subscriptions.action_cancel"))
        elif is_cancelled or sub.status.value == "muted":
            ui.button(
                icon="refresh",
                on_click=lambda _e, sid=sub.id: on_reactivate(sid),
            ).props("flat dense round color=primary").tooltip(t("subscriptions.action_reactivate"))
        ui.button(
            icon="delete",
            on_click=lambda _e, s=sub: on_delete(s),
        ).props("flat dense round color=negative").tooltip(t("subscriptions.action_delete"))


def _render_sub_row_subtitle(sub: SubscriptionResponse) -> None:
    parts: list[str] = [cadence_label(sub.cadence_days)]
    if sub.status.value == "muted" and sub.muted_until:
        parts.append(t("subscriptions.muted_until", date=fmt_date(sub.muted_until)))
    elif sub.status.value == "cancelled" and sub.cancelled_at:
        parts.append(t("subscriptions.cancelled_on", date=fmt_date(sub.cancelled_at)))
    elif sub.next_expected_at:
        parts.append(fmt_date(sub.next_expected_at))
    ui.label(" · ".join(parts)).classes("text-xs text-slate-500")


def _render_sub_row_notes(sub: SubscriptionResponse) -> None:
    """Inline note block under the subtitle — collapsed preview expands on click."""
    if not sub.notes:
        return
    preview = build_notes_preview(sub.notes)

    preview_row = ui.row().classes(
        "items-center gap-1 mt-0.5" + (" cursor-pointer" if preview.can_toggle else "")
    )
    with preview_row:
        ui.icon("sticky_note_2", size="0.9rem").classes("text-slate-500")
        ui.label(preview.preview_text).classes("text-xs text-slate-500")

    full_row = ui.row().classes("items-start gap-1 mt-0.5 cursor-pointer")
    full_row.set_visibility(False)
    with full_row:
        ui.icon("sticky_note_2", size="0.9rem").classes("text-slate-500 mt-0.5")
        ui.label(preview.full_text).classes(
            "text-xs text-slate-500 whitespace-pre-line leading-snug"
        )

    if preview.can_toggle:

        def _toggle(_e: Any = None) -> None:
            preview_row.set_visibility(not preview_row.visible)
            full_row.set_visibility(not full_row.visible)

        preview_row.on("click", _toggle)
        full_row.on("click", _toggle)
