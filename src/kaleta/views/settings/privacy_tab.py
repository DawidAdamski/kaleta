# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings — Privacy & diagnostics tab (UI surface for observability plan)."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.config import settings as app_settings
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.services import BugReportService, with_session
from kaleta.views.bug_report_dialog import open_bug_report_dialog
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.settings.constants import DEFAULT_EVENT_RETENTION_DAYS, DEFAULT_EVENTS_ENABLED
from kaleta.views.settings.helpers import set_user_key

_STATUS_KEYS = {"new": "bugreport.status_new", "seen": "bugreport.status_seen"}


def _status_label(status: object) -> str:
    return t(_STATUS_KEYS.get(str(status), "bugreport.status_closed"))


async def _load_my_reports() -> list[dict[str, Any]]:
    user_id = app.storage.user.get(SESSION_USER_ID)
    if user_id is None:
        return []

    async def _query(session: Any) -> list[dict[str, Any]]:
        reports = await BugReportService(session).list(user_id=int(user_id), limit=20)
        return [
            {
                "report_id": report.report_id,
                "created_at": report.created_at.strftime("%Y-%m-%d %H:%M"),
                "summary": report.summary,
                "status": _status_label(report.status),
            }
            for report in reports
        ]

    return await with_session(_query)


async def _delete_report(report_id: str) -> None:
    user_id = app.storage.user.get(SESSION_USER_ID)

    async def _run(session: Any) -> None:
        await BugReportService(session).delete(
            report_id,
            user_id=int(user_id) if user_id is not None else None,
        )

    await with_session(_run)


def _trigger_test_error() -> None:
    """Debug-only: walk the real failure path so the tray can be seen."""
    notify_kaleta_error(KaletaError(t("settings.test_error_message")))


async def render_privacy_tab() -> None:
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

            with ui.row().classes("w-full items-center gap-3 flex-wrap mt-4"):
                ui.button(
                    t("bugreport.menu_item"),
                    icon="bug_report",
                    on_click=open_bug_report_dialog,
                ).props("color=primary unelevated")
                if app_settings.debug:
                    ui.button(
                        t("settings.trigger_test_error"),
                        icon="science",
                        on_click=_trigger_test_error,
                    ).props("outline color=negative")

            if app_settings.debug:
                ui.label(t("settings.trigger_test_error_hint")).classes(
                    "text-xs text-slate-500 mt-2"
                )

        with ui.card().classes("p-6 w-full"):
            with ui.row().classes("items-center gap-2 mb-1"):
                ui.icon("forum", color="primary").classes("text-xl")
                ui.label(t("bugreport.my_reports_title")).classes("text-lg font-semibold")
            ui.label(t("bugreport.my_reports_hint")).classes("text-xs text-slate-500 mb-4")

            reports_container = ui.column().classes("w-full gap-2")

            async def _refresh() -> None:
                rows = await _load_my_reports()
                reports_container.clear()
                with reports_container:
                    if not rows:
                        ui.label(t("bugreport.my_reports_empty")).classes("text-sm text-slate-500")
                        return
                    for row in rows:
                        with ui.row().classes("w-full items-center gap-3 flex-wrap"):
                            ui.label(row["report_id"]).classes("text-sm k-mono w-24")
                            ui.label(row["created_at"]).classes("text-xs text-slate-500 w-32")
                            ui.label(row["summary"]).classes("text-sm flex-grow")
                            ui.label(row["status"]).classes("text-xs text-slate-500")
                            delete_label = t("bugreport.delete_report")
                            ui.button(
                                icon="delete",
                                on_click=lambda _=None, rid=row["report_id"]: _remove(rid),
                            ).props(
                                f'flat dense round color=negative aria-label="{delete_label}"'
                            ).tooltip(delete_label)

            async def _remove(report_id: str) -> None:
                try:
                    await _delete_report(report_id)
                except KaletaError as exc:
                    notify_kaleta_error(exc)
                    return
                ui.notify(t("bugreport.deleted"), type="positive")
                await _refresh()

            await _refresh()
