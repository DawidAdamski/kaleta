# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — General tab (language, currency, date format, week start)."""

from __future__ import annotations

import datetime

from nicegui import app, ui

from kaleta.i18n import available_languages, t
from kaleta.views.accounts import COMMON_CURRENCIES
from kaleta.views.settings.constants import DEFAULT_DATE_FORMAT, DEFAULT_WEEK_START
from kaleta.views.settings.helpers import set_user_key


def render_general_tab() -> None:
    with ui.row().classes("w-full gap-6 flex-wrap items-start"):
        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("language", color="primary").classes("text-xl")
                ui.label(t("settings.language")).classes("text-lg font-semibold")

            langs = available_languages()
            current_lang: str = app.storage.user.get("language", "en")

            def _set_language(lang: str) -> None:
                app.storage.user["language"] = lang
                ui.navigate.reload()

            ui.select(
                langs,
                label=t("settings.language_label"),
                value=current_lang,
                on_change=lambda e: _set_language(e.value),
            ).classes("w-full")
            ui.label(t("settings.language_hint")).classes("text-xs text-grey-6 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("currency_exchange", color="primary").classes("text-xl")
                ui.label(t("settings.currency")).classes("text-lg font-semibold")

            default_currency: str = app.storage.user.get("currency", "PLN")

            def _set_currency(currency: str) -> None:
                app.storage.user["currency"] = currency
                ui.navigate.reload()

            ui.select(
                COMMON_CURRENCIES,
                label=t("settings.currency_label"),
                value=default_currency,
                on_change=lambda e: _set_currency(e.value),
            ).classes("w-full")
            ui.label(t("settings.currency_hint")).classes("text-xs text-grey-6 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("event", color="primary").classes("text-xl")
                ui.label(t("settings.date_format")).classes("text-lg font-semibold")

            current_fmt: str = app.storage.user.get("date_format", DEFAULT_DATE_FORMAT)
            today = datetime.date.today()
            preview = {
                "iso": today.isoformat(),
                "eu": today.strftime("%d.%m.%Y"),
                "us": today.strftime("%m/%d/%Y"),
            }
            ui.select(
                {
                    "iso": f"ISO — {preview['iso']}",
                    "eu": f"EU — {preview['eu']}",
                    "us": f"US — {preview['us']}",
                },
                label=t("settings.date_format_label"),
                value=current_fmt,
                on_change=lambda e: set_user_key("date_format", e.value),
            ).classes("w-full")
            ui.label(t("settings.date_format_hint")).classes("text-xs text-grey-6 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("calendar_view_week", color="primary").classes("text-xl")
                ui.label(t("settings.week_start")).classes("text-lg font-semibold")

            current_ws: str = app.storage.user.get("week_start", DEFAULT_WEEK_START)
            ui.select(
                {
                    "monday": t("settings.week_start_monday"),
                    "sunday": t("settings.week_start_sunday"),
                },
                label=t("settings.week_start_label"),
                value=current_ws,
                on_change=lambda e: set_user_key("week_start", e.value),
            ).classes("w-full")
            ui.label(t("settings.week_start_hint")).classes("text-xs text-grey-6 mt-2")
