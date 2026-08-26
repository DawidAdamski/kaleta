# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Privacy & diagnostics tab (UI surface for observability plan)."""

from __future__ import annotations

from nicegui import app, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.i18n import t
from kaleta.views.settings.constants import DEFAULT_EVENT_RETENTION_DAYS, DEFAULT_EVENTS_ENABLED
from kaleta.views.settings.helpers import set_user_key


def render_privacy_tab() -> None:
    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("shield", color="primary").classes("text-xl")
                ui.label(t("settings.privacy_title")).classes("text-lg font-semibold")
            ui.label(t("settings.privacy_hint")).classes("text-xs text-slate-500 mb-4")

            events_enabled = bool(app.storage.user.get("events_enabled", DEFAULT_EVENTS_ENABLED))
            ui.switch(
                t("settings.events_enabled"),
                value=events_enabled,
                on_change=lambda e: set_user_key("events_enabled", bool(e.value)),
            )

            retention_days = int(
                app.storage.user.get("event_retention_days", DEFAULT_EVENT_RETENTION_DAYS)
            )
            ui.number(
                t("settings.event_retention_days"),
                value=retention_days,
                min=1,
                max=90,
                step=1,
                on_change=lambda e: set_user_key("event_retention_days", int(e.value or 0)),
            ).classes("max-w-60 mt-4")

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("bug_report", color="primary").classes("text-xl")
                ui.label(t("settings.diagnostics_title")).classes("text-lg font-semibold")
            ui.label(t("settings.diagnostics_hint")).classes("text-xs text-slate-500 mb-4")

            user_id = app.storage.user.get(SESSION_USER_ID)
            client_id = getattr(getattr(ui.context, "client", None), "id", None)
            session_label = str(user_id) if user_id is not None else str(client_id or "—")

            with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                ui.label(t("settings.session_id_label")).classes("text-sm text-slate-500")
                ui.label(session_label).classes("text-sm font-mono")
                ui.button(
                    t("settings.copy_session_id"),
                    icon="content_copy",
                    on_click=lambda: ui.run_javascript(
                        f"navigator.clipboard.writeText({session_label!r})"
                    ),
                ).props("outline color=primary")

            ui.label(t("settings.session_id_hint")).classes("text-xs text-slate-500 mt-2")
