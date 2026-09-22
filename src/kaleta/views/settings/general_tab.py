# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — General tab (language, currency, date format, week start)."""

from __future__ import annotations

import datetime

from nicegui import app, ui

from kaleta.core.weeks import WeekStartMode
from kaleta.i18n import available_languages, t
from kaleta.views.accounts import COMMON_CURRENCIES
from kaleta.views.settings.constants import (
    DEFAULT_BUDGET_MONTH_START_DAY,
    DEFAULT_DATE_FORMAT,
    DEFAULT_NUMBER_FORMAT,
    DEFAULT_WEEK_START,
    DEFAULT_WEEK_START_MODE,
)
from kaleta.views.settings.helpers import set_user_key


def render_general_tab(*, account_options: dict[int, str] | None = None) -> None:
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
            ui.label(t("settings.language_hint")).classes("text-xs text-slate-500 mt-2")

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
            ui.label(t("settings.currency_hint")).classes("text-xs text-slate-500 mt-2")

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
            ui.label(t("settings.date_format_hint")).classes("text-xs text-slate-500 mt-2")

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
            ui.label(t("settings.week_start_hint")).classes("text-xs text-slate-500 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("date_range", color="primary").classes("text-xl")
                ui.label(t("settings.week_start_mode")).classes("text-lg font-semibold")

            current_wsm: str = app.storage.user.get("week_start_mode", DEFAULT_WEEK_START_MODE)

            def _set_week_start_mode(value: object) -> None:
                # Every weekly subtotal on screen was bucketed under the old
                # answer, so the pages have to be drawn again — saving quietly
                # would leave the ledger showing weeks the setting no longer means.
                app.storage.user["week_start_mode"] = str(value)
                ui.navigate.reload()

            ui.select(
                {
                    WeekStartMode.ISO_MONDAY.value: t("settings.week_start_mode_iso"),
                    WeekStartMode.MONTH_DAY_1.value: t("settings.week_start_mode_month"),
                },
                label=t("settings.week_start_mode_label"),
                value=current_wsm,
                on_change=lambda e: _set_week_start_mode(e.value),
            ).classes("w-full")
            ui.label(t("settings.week_start_mode_hint")).classes("text-xs text-slate-500 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("123", color="primary").classes("text-xl")
                ui.label(t("settings.number_format")).classes("text-lg font-semibold")

            current_nf: str = app.storage.user.get("number_format", DEFAULT_NUMBER_FORMAT)
            ui.select(
                {
                    "eu": t("settings.number_format_eu"),
                    "us": t("settings.number_format_us"),
                },
                label=t("settings.number_format_label"),
                value=current_nf,
                on_change=lambda e: set_user_key("number_format", e.value),
            ).classes("w-full")
            ui.label(t("settings.number_format_hint")).classes("text-xs text-slate-500 mt-2")

        with ui.card().classes("p-6 min-w-72 w-80"):
            with ui.row().classes("items-center gap-2 mb-4"):
                ui.icon("calendar_month", color="primary").classes("text-xl")
                ui.label(t("settings.budget_month_start")).classes("text-lg font-semibold")

            current_bms: int = int(
                app.storage.user.get("budget_month_start_day", DEFAULT_BUDGET_MONTH_START_DAY)
            )
            ui.number(
                t("settings.budget_month_start_label"),
                value=current_bms,
                min=1,
                max=28,
                step=1,
                on_change=lambda e: set_user_key("budget_month_start_day", int(e.value or 1)),
            ).classes("w-full")
            ui.label(t("settings.budget_month_start_hint")).classes("text-xs text-slate-500 mt-2")

        if account_options:
            with ui.card().classes("p-6 min-w-72 w-80"):
                with ui.row().classes("items-center gap-2 mb-4"):
                    ui.icon("account_balance_wallet", color="primary").classes("text-xl")
                    ui.label(t("settings.default_account")).classes("text-lg font-semibold")

                none_label = t("settings.default_account_none")
                options: dict[int, str] = {0: none_label}
                options.update(account_options)
                current_da = app.storage.user.get("default_account_id")
                current_val = int(current_da) if isinstance(current_da, (int, str)) else 0

                def _set_default_account(value: object) -> None:
                    int_value = int(value) if isinstance(value, (int, str)) else 0
                    if int_value == 0:
                        app.storage.user.pop("default_account_id", None)
                        ui.notify(t("settings.saved"), type="positive")
                    else:
                        set_user_key("default_account_id", int_value)

                ui.select(
                    options,
                    label=t("settings.default_account_label"),
                    value=current_val if current_val in options else 0,
                    on_change=lambda e: _set_default_account(e.value),
                ).classes("w-full")
                ui.label(t("settings.default_account_hint")).classes("text-xs text-slate-500 mt-2")
