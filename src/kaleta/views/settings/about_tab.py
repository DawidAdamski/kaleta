# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — About tab."""

from __future__ import annotations

import json

from nicegui import app, ui

from kaleta.config.settings import settings as app_settings
from kaleta.debug_info import DebugSection, build_sections, sections_as_markdown
from kaleta.i18n import t
from kaleta.views.settings.helpers import about_row

#: Keys whose values the panel may show: the ones the user picked themselves
#: on the General and Features tabs. Everything else in session storage is
#: listed by type only — see ``debug_info.build_sections``.
_FEATURE_KEYS = (
    "language",
    "currency",
    "date_format",
    "number_format",
    "week_start",
    "week_start_mode",
    "budget_month_start_day",
    "transactions_upcoming_days",
    "transfer_pairing_days",
    "transfer_amount_tolerance",
    "payee_dedupe_max_distance",
    "subscriptions_detector_days",
    "housekeeping_duplicate_days",
    "auto_post_due_on_startup",
    "import_skip_duplicates_default",
    "events_enabled",
    "event_retention_days",
)


def _storage_types() -> dict[str, str]:
    """Every key this session holds, named with the type of what is under it."""
    try:
        keys = list(app.storage.user.keys())
    except Exception:
        # No request context (a smoke import, a background task) — the panel
        # is still worth rendering without this one section.
        return {}
    return {str(key): type(app.storage.user.get(key)).__name__ for key in sorted(keys)}


def _feature_values() -> dict[str, str]:
    """The knobs the user set, as they were set — none of them is a secret."""
    values: dict[str, str] = {}
    try:
        for key in _FEATURE_KEYS:
            if key in app.storage.user:
                values[key] = str(app.storage.user.get(key))
    except Exception:
        return {}
    return values


def _render_section(section: DebugSection) -> None:
    ui.label(section.title).classes("text-sm font-semibold mt-3")
    if section.rows:
        with ui.column().classes("gap-0 w-full"):
            for key, value in section.rows:
                about_row(key, value or "—")
    elif section.lines:
        ui.code("\n".join(section.lines)).classes("w-full text-xs")
    else:
        ui.label(section.empty_note).classes("text-xs text-slate-400")


def render_about_tab() -> None:
    with ui.card().classes("p-6 w-full"):
        with ui.row().classes("items-center gap-2 mb-4"):
            ui.icon("info", color="primary").classes("text-xl")
            ui.label(t("settings.about_title")).classes("text-lg font-semibold")

        with ui.column().classes("gap-1"):
            about_row(t("settings.about_mode"), app_settings.mode)
            about_row(t("settings.about_debug"), "yes" if app_settings.debug else "no")
            about_row(t("settings.about_host"), app_settings.host)
            about_row(t("settings.about_port"), str(app_settings.port))

        ui.separator().classes("my-4")

        with ui.row().classes("gap-3 flex-wrap"):
            ui.button(
                t("settings.about_github"),
                icon="code",
                on_click=lambda: ui.navigate.to(
                    "https://github.com/DawidAdamski/kaleta", new_tab=True
                ),
            ).props("outline color=primary")
            ui.button(
                t("settings.about_docs"),
                icon="menu_book",
                on_click=lambda: ui.navigate.to("/docs", new_tab=True),
            ).props("outline color=primary")

    if app_settings.debug:
        _render_debug_card()


def _render_debug_card() -> None:
    """The panel behind ``KALETA_DEBUG`` — everything an issue needs.

    Only under debug: the report names the configuration in force, and on a
    shared instance that is not a page to leave open to whoever signs in.
    """
    with ui.card().classes("p-6 w-full mt-4"):
        with ui.row().classes("items-center gap-2 mb-1"):
            ui.icon("bug_report", color="primary").classes("text-xl")
            ui.label(t("settings.debug_title")).classes("text-lg font-semibold")
        ui.label(t("settings.debug_hint")).classes("text-xs text-slate-500 mb-2")

        sections = build_sections(
            storage_keys=_storage_types(),
            feature_flags=_feature_values(),
        )

        def _copy() -> None:
            markdown = sections_as_markdown(
                build_sections(
                    storage_keys=_storage_types(),
                    feature_flags=_feature_values(),
                )
            )
            # Rebuilt on click rather than reusing the rendered sections: the
            # log tail and the session keys move while the page is open, and a
            # report pasted into an issue should be what the user sees now.
            ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(markdown)})")
            ui.notify(t("settings.debug_copied"), type="positive")

        with ui.row().classes("gap-3 flex-wrap mb-2"):
            ui.button(
                t("settings.debug_copy"),
                icon="content_copy",
                on_click=_copy,
            ).props("color=primary")

        with ui.expansion(t("settings.debug_details"), icon="list").classes("w-full"):
            for section in sections:
                _render_section(section)
