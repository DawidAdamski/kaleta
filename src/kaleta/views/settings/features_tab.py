# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Features tab (wizard, detector windows)."""

from __future__ import annotations

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.views.settings.constants import (
    DEFAULT_HOUSEKEEPING_DUPLICATE_DAYS,
    DEFAULT_PAYMENT_CALENDAR_OVERDUE_DAYS,
    DEFAULT_SUBSCRIPTIONS_DETECTOR_DAYS,
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
