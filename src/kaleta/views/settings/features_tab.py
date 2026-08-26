# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Features tab (wizard, detector windows)."""

from __future__ import annotations

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.views.settings.constants import (
    DEFAULT_AUTO_POST_DUE_ON_STARTUP,
    DEFAULT_HOUSEKEEPING_DUPLICATE_DAYS,
    DEFAULT_IMPORT_SKIP_DUPLICATES,
    DEFAULT_PAYEE_DEDUPE_MAX_DISTANCE,
    DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS,
    DEFAULT_SUBSCRIPTIONS_DETECTOR_DAYS,
    DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    DEFAULT_TRANSFER_PAIRING_DAYS,
)
from kaleta.views.settings.helpers import set_user_key


def render_features_tab() -> None:
    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("auto_awesome", color="primary").classes("text-xl")
                ui.label(t("settings.wizard_title")).classes("text-lg font-semibold")
            ui.label(t("settings.wizard_hint")).classes("text-xs text-slate-500 mb-4")

            def _reset_getting_started() -> None:
                app.storage.user["wizard_mentor_dismissed"] = []
                app.storage.user["wizard_onboarding_open"] = True
                ui.notify(t("settings.wizard_reset_done"), type="positive")

            ui.button(
                t("settings.wizard_reset_btn"),
                icon="replay",
                on_click=_reset_getting_started,
            ).props("color=primary outline")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("subscriptions", color="primary").classes("text-xl")
                ui.label(t("settings.subscriptions_title")).classes("text-lg font-semibold")
            ui.label(t("settings.subscriptions_hint")).classes("text-xs text-slate-500 mb-4")

            current_sub_days: int = int(
                app.storage.user.get(
                    "subscriptions_detector_days",
                    DEFAULT_SUBSCRIPTIONS_DETECTOR_DAYS,
                )
            )
            ui.number(
                t("settings.subscriptions_detector_days"),
                value=current_sub_days,
                min=30,
                max=1825,
                step=30,
                on_change=lambda e: set_user_key("subscriptions_detector_days", int(e.value or 0)),
            ).classes("max-w-60")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("cleaning_services", color="primary").classes("text-xl")
                ui.label(t("settings.housekeeping_title")).classes("text-lg font-semibold")
            ui.label(t("settings.housekeeping_hint")).classes("text-xs text-slate-500 mb-4")

            current_hk_days: int = int(
                app.storage.user.get(
                    "housekeeping_duplicate_days",
                    DEFAULT_HOUSEKEEPING_DUPLICATE_DAYS,
                )
            )
            ui.number(
                t("settings.housekeeping_duplicate_days"),
                value=current_hk_days,
                min=30,
                max=1825,
                step=30,
                on_change=lambda e: set_user_key("housekeeping_duplicate_days", int(e.value or 0)),
            ).classes("max-w-60")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("calendar_month", color="primary").classes("text-xl")
                ui.label(t("settings.payment_calendar_title")).classes("text-lg font-semibold")
            ui.label(t("settings.payment_calendar_hint")).classes("text-xs text-slate-500 mb-4")

            current_pc_days: int = int(
                app.storage.user.get(
                    "payment_calendar_overdue_days",
                    DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS,
                )
            )
            ui.number(
                t("settings.payment_calendar_overdue_days"),
                value=current_pc_days,
                min=1,
                max=180,
                step=1,
                on_change=lambda e: set_user_key(
                    "payment_calendar_overdue_days", int(e.value or 0)
                ),
            ).classes("max-w-60")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("publish", color="primary").classes("text-xl")
                ui.label(t("settings.auto_post_due_title")).classes("text-lg font-semibold")
            ui.label(t("settings.auto_post_due_hint")).classes("text-xs text-slate-500 mb-4")

            auto_post = bool(
                app.storage.user.get(
                    "auto_post_due_on_startup",
                    DEFAULT_AUTO_POST_DUE_ON_STARTUP,
                )
            )
            ui.switch(
                t("settings.auto_post_due"),
                value=auto_post,
                on_change=lambda e: set_user_key("auto_post_due_on_startup", bool(e.value)),
            )

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("swap_horiz", color="primary").classes("text-xl")
                ui.label(t("settings.transfer_pairing_title")).classes("text-lg font-semibold")
            ui.label(t("settings.transfer_pairing_hint")).classes("text-xs text-slate-500 mb-4")

            pairing_days = int(
                app.storage.user.get("transfer_pairing_days", DEFAULT_TRANSFER_PAIRING_DAYS)
            )
            ui.number(
                t("settings.transfer_pairing_days"),
                value=pairing_days,
                min=0,
                max=30,
                step=1,
                on_change=lambda e: set_user_key("transfer_pairing_days", int(e.value or 0)),
            ).classes("max-w-60")

            tolerance = float(
                app.storage.user.get("transfer_amount_tolerance", DEFAULT_TRANSFER_AMOUNT_TOLERANCE)
            )
            ui.number(
                t("settings.transfer_amount_tolerance"),
                value=tolerance,
                min=0,
                max=100,
                step=0.01,
                format="%.2f",
                on_change=lambda e: set_user_key(
                    "transfer_amount_tolerance", f"{float(e.value or 0):.2f}"
                ),
            ).classes("max-w-60 mt-2")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("groups", color="primary").classes("text-xl")
                ui.label(t("settings.payee_dedupe_title")).classes("text-lg font-semibold")
            ui.label(t("settings.payee_dedupe_hint")).classes("text-xs text-slate-500 mb-4")

            dedupe_dist = int(
                app.storage.user.get("payee_dedupe_max_distance", DEFAULT_PAYEE_DEDUPE_MAX_DISTANCE)
            )
            ui.number(
                t("settings.payee_dedupe_max_distance"),
                value=dedupe_dist,
                min=1,
                max=5,
                step=1,
                on_change=lambda e: set_user_key("payee_dedupe_max_distance", int(e.value or 0)),
            ).classes("max-w-60")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("upload_file", color="primary").classes("text-xl")
                ui.label(t("settings.import_defaults_title")).classes("text-lg font-semibold")
            ui.label(t("settings.import_defaults_hint")).classes("text-xs text-slate-500 mb-4")

            skip_default = bool(
                app.storage.user.get(
                    "import_skip_duplicates_default", DEFAULT_IMPORT_SKIP_DUPLICATES
                )
            )
            ui.switch(
                t("settings.import_skip_duplicates_default"),
                value=skip_default,
                on_change=lambda e: set_user_key("import_skip_duplicates_default", bool(e.value)),
            )
