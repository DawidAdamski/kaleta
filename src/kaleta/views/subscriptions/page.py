"""Subscriptions page — routing, layout, and section wiring."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.subscription import SubscriptionResponse
from kaleta.services import CategoryService, SubscriptionService, with_session
from kaleta.views.layout import page_layout
from kaleta.views.subscriptions.dialogs import build_subscription_dialogs
from kaleta.views.subscriptions.helpers import fmt_amount
from kaleta.views.subscriptions.rows import (
    render_candidate_row,
    render_category_group,
    render_renewal_row,
    render_sub_row,
)
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING


async def subscriptions_page() -> None:
    detector_days = int(app.storage.user.get("subscriptions_detector_days", 0) or 0) or None

    async def _load_page_data(session: Any) -> tuple[Any, ...]:
        cat_svc = CategoryService(session)
        await cat_svc.ensure_subscriptions_root_and_children()
        svc = SubscriptionService(session)
        subs = await svc.list()
        totals = await svc.totals()
        candidates = await svc.detect_candidates(window_days=detector_days)
        renewals = await svc.upcoming_renewals(days=30)
        by_category = await svc.subscription_transactions_grouped()
        expense_cats = await cat_svc.list()
        sub_children = await cat_svc.list_subscription_children()
        sub_root = await cat_svc.get_subscriptions_root()
        return (
            subs,
            totals,
            candidates,
            renewals,
            by_category,
            expense_cats,
            sub_children,
            sub_root,
        )

    (
        subs,
        totals,
        candidates,
        renewals,
        by_category,
        expense_cats,
        sub_children,
        sub_root,
    ) = await with_session(_load_page_data)

    sub_responses = [SubscriptionResponse.model_validate(s) for s in subs]
    category_opts = CategoryService.build_option_labels(
        [c for c in expense_cats if c.type.value == "expense"]
    )
    sub_category_opts = CategoryService.build_option_labels(sub_children)

    with page_layout(t("subscriptions.title"), wide=True):
        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(t("subscriptions.title")).classes(PAGE_TITLE)
                ui.label(t("subscriptions.subtitle")).classes(BODY_MUTED)
            with ui.row().classes("items-center gap-3"):
                ui.badge(
                    t("subscriptions.active_count", count=totals.active_count),
                    color="primary",
                ).classes("text-sm px-3 py-1")
                with ui.column().classes("items-end gap-0"):
                    ui.label(
                        t("subscriptions.total_monthly", amount=fmt_amount(totals.monthly_total))
                    ).classes("text-base font-semibold")
                    ui.label(
                        t("subscriptions.total_yearly", amount=fmt_amount(totals.yearly_total))
                    ).classes("text-xs text-slate-500")

        (
            open_add_dialog,
            open_edit_dialog,
            open_delete_dialog,
            confirm_candidate,
            dismiss_candidate,
            mute,
            cancel,
            reactivate,
        ) = build_subscription_dialogs(
            category_opts=category_opts,
            sub_category_opts=sub_category_opts,
            detector_days=detector_days,
        )

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button(
                t("subscriptions.manage_categories"),
                icon="category",
                on_click=lambda: ui.navigate.to("/categories"),
            ).props("flat color=primary size=sm")
            ui.button(t("subscriptions.add"), icon="add", on_click=open_add_dialog).props(
                "color=primary unelevated size=sm"
            )

        with ui.card().classes(SECTION_CARD):
            with ui.row().classes("items-center justify-between w-full"):
                with ui.column().classes("gap-0"):
                    ui.label(t("subscriptions.by_category_heading")).classes(SECTION_HEADING)
                    ui.label(t("subscriptions.by_category_hint")).classes(BODY_MUTED)
                if sub_root is not None:
                    ui.label(t("subscriptions.by_category_root", name=sub_root.name)).classes(
                        "text-xs text-slate-500"
                    )
            if not by_category:
                ui.label(t("subscriptions.by_category_empty")).classes(f"{BODY_MUTED} mt-2")
            else:
                for group in by_category:
                    render_category_group(group)

        with ui.card().classes(SECTION_CARD):
            ui.label(t("subscriptions.detector_heading")).classes(SECTION_HEADING)
            ui.label(t("subscriptions.detector_hint")).classes(BODY_MUTED)
            if not candidates:
                ui.label(t("subscriptions.detector_empty")).classes(f"{BODY_MUTED} mt-2")
            else:
                for cand in candidates:
                    render_candidate_row(cand, confirm_candidate, dismiss_candidate)

        with ui.card().classes(SECTION_CARD):
            ui.label(t("subscriptions.renewals_heading")).classes(SECTION_HEADING)
            if not renewals:
                ui.label(t("subscriptions.renewals_empty")).classes(f"{BODY_MUTED} mt-2")
            else:
                for renewal in renewals:
                    render_renewal_row(renewal)

        with ui.card().classes(SECTION_CARD):
            ui.label(t("subscriptions.active_heading")).classes(SECTION_HEADING)
            if not sub_responses:
                ui.label(t("subscriptions.active_empty")).classes(f"{BODY_MUTED} mt-2")
            else:
                for sub in sub_responses:
                    render_sub_row(
                        sub,
                        on_edit=open_edit_dialog,
                        on_mute=mute,
                        on_cancel=cancel,
                        on_reactivate=reactivate,
                        on_delete=open_delete_dialog,
                    )
