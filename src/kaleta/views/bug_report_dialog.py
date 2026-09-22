# SPDX-License-Identifier: AGPL-3.0-or-later
"""The "Report a problem" dialog — the only way ledger words leave the app.

Everything the report carries is shown before it is sent: the version, the
route, the browser, and the event ids this session collected. The log excerpt
is off unless the user ticks the box, and the description is theirs alone.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode

from nicegui import app, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.observability import SessionRingBuffer, app_version
from kaleta.services import BugReportService, with_session
from kaleta.services.bug_report_delivery import schedule_delivery, webhook_includes_logs
from kaleta.services.bug_report_service import webhook_payload
from kaleta.views.error_handling import (
    current_client_id,
    notify_kaleta_error,
    session_event_ids,
)

logger = logging.getLogger(__name__)

GITHUB_NEW_ISSUE = "https://github.com/DawidAdamski/kaleta/issues/new"

_BROWSER_CONTEXT_JS = (
    "JSON.stringify({"
    "user_agent: navigator.userAgent,"
    "viewport: window.innerWidth + 'x' + window.innerHeight,"
    "locale: navigator.language,"
    "route: window.location.pathname"
    "})"
)

#: One dialog per connected client; replaced whenever a page is built.
_dialogs: dict[str, BugReportDialog] = {}


def github_issue_url(
    *,
    report_id: str,
    summary: str,
    event_ids: list[str],
    version: str,
    route: str | None,
) -> str:
    """Prefilled issue form — never the description or the log excerpt."""
    query = urlencode(
        {
            "template": "bug.yml",
            "title": f"[Bug]: {summary} ({report_id})"[:120],
            "report_id": report_id,
            "version": version,
            "route": route or "",
            "events": ", ".join(event_ids),
        }
    )
    return f"{GITHUB_NEW_ISSUE}?{query}"


class BugReportDialog:
    """Form, then confirmation — the same dialog in two states."""

    def __init__(self) -> None:
        self._event_ids: list[str] = []
        self._browser: dict[str, str] = {}
        self._report_id = ""
        self._summary_sent = ""

        with ui.dialog() as self.dialog, ui.card().classes("w-[560px] max-w-full gap-3 p-6"):
            with ui.column().classes("w-full gap-3") as self._form:
                ui.label(t("bugreport.title")).classes("text-lg font-bold")
                ui.label(t("bugreport.intro")).classes("text-xs text-slate-500")
                self._summary = (
                    ui.input(t("bugreport.summary_label")).props("maxlength=120").classes("w-full")
                )
                self._description = (
                    ui.textarea(t("bugreport.description_label"))
                    .props("autogrow")
                    .classes("w-full")
                )
                self._contact = ui.input(t("bugreport.contact_label")).classes("w-full")

                ui.label(t("bugreport.events_label")).classes("text-xs font-semibold mt-2")
                self._chips = ui.row().classes("w-full gap-2 flex-wrap")

                ui.label(t("bugreport.context_label")).classes("text-xs font-semibold mt-2")
                self._context = ui.column().classes("w-full gap-0")

                self._attach_logs = ui.checkbox(t("bugreport.attach_logs"), value=False)
                ui.label(t("bugreport.privacy_note")).classes("text-xs text-slate-500")

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=self.dialog.close).props("flat")
                    ui.button(
                        t("bugreport.submit"),
                        icon="send",
                        on_click=self._submit,
                    ).props("color=primary unelevated")

            with ui.column().classes("w-full gap-3") as self._confirmation:
                ui.label(t("bugreport.submitted_title")).classes("text-lg font-bold")
                ui.label(t("bugreport.submitted_hint")).classes("text-xs text-slate-500")
                self._report_label = ui.label("").classes("k-mono text-base font-semibold")
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(
                        t("bugreport.copy_report_id"),
                        icon="content_copy",
                        on_click=self._copy_report_id,
                    ).props("flat")
                    ui.button(
                        t("bugreport.open_github"),
                        icon="open_in_new",
                        on_click=self._open_github,
                    ).props("outline color=primary")
                    ui.button(t("common.close"), on_click=self.dialog.close).props(
                        "color=primary unelevated"
                    )
        self._confirmation.set_visibility(False)

    async def open(self) -> None:
        """Reset to the form, collect the browser context, and show it."""
        self._confirmation.set_visibility(False)
        self._form.set_visibility(True)
        self._summary.set_value("")
        self._description.set_value("")
        self._attach_logs.set_value(False)
        self._event_ids = session_event_ids()
        self._browser = await self._read_browser_context()
        self._render_chips()
        self._render_context()
        self.dialog.open()

    async def _read_browser_context(self) -> dict[str, str]:
        try:
            raw = await ui.run_javascript(_BROWSER_CONTEXT_JS, timeout=5.0)
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            logger.debug("Could not read the browser context for a bug report")
            return {}
        return {str(key): str(value) for key, value in dict(parsed).items()}

    def _render_chips(self) -> None:
        self._chips.clear()
        with self._chips:
            if not self._event_ids:
                ui.label(t("bugreport.no_events")).classes("text-xs text-slate-500")
                return
            for event_id in list(self._event_ids):
                chip = ui.chip(event_id, removable=True, icon="bug_report").props("outline dense")
                chip.on("remove", lambda _=None, e=event_id: self._drop_event(e))

    def _drop_event(self, event_id: str) -> None:
        self._event_ids = [item for item in self._event_ids if item != event_id]

    def _render_context(self) -> None:
        self._context.clear()
        rows = [
            (t("bugreport.context_version"), app_version()),
            (t("bugreport.context_route"), self._browser.get("route", "—")),
            (t("bugreport.context_browser"), self._browser.get("user_agent", "—")),
            (t("bugreport.context_viewport"), self._browser.get("viewport", "—")),
            (t("bugreport.context_locale"), self._browser.get("locale", "—")),
        ]
        with self._context:
            for label, value in rows:
                with ui.row().classes("w-full items-start gap-2 flex-nowrap"):
                    ui.label(label).classes("text-xs text-slate-500 w-24 shrink-0")
                    ui.label(value).classes("text-xs k-mono break-all")

    async def _submit(self) -> None:
        client_id = current_client_id()
        log_records: list[dict[str, Any]] | None = None
        if self._attach_logs.value:
            log_records = SessionRingBuffer.records(client_id)

        summary = str(self._summary.value or "")
        event_ids = list(self._event_ids)

        async def _create(session: Any) -> Any:
            return await BugReportService(session).create(
                summary=summary,
                description=str(self._description.value or ""),
                event_ids=event_ids,
                route=self._browser.get("route"),
                user_agent=self._browser.get("user_agent"),
                viewport=self._browser.get("viewport"),
                locale=self._browser.get("locale"),
                contact_email=str(self._contact.value or ""),
                session_id=client_id,
                user_id=app.storage.user.get(SESSION_USER_ID),
                log_records=log_records,
            )

        try:
            report = await with_session(_create)
        except KaletaError as exc:
            notify_kaleta_error(exc)
            return

        schedule_delivery(webhook_payload(report, include_logs=webhook_includes_logs()))

        self._report_id = report.report_id
        self._summary_sent = report.summary
        self._report_label.set_text(t("bugreport.report_id_label", report_id=report.report_id))
        self._form.set_visibility(False)
        self._confirmation.set_visibility(True)

    def _copy_report_id(self) -> None:
        ui.run_javascript(f"navigator.clipboard.writeText({self._report_id!r})")
        ui.notify(t("bugreport.copied"), type="positive")

    def _open_github(self) -> None:
        ui.navigate.to(
            github_issue_url(
                report_id=self._report_id,
                summary=self._summary_sent,
                event_ids=self._event_ids,
                version=app_version(),
                route=self._browser.get("route"),
            ),
            new_tab=True,
        )


def install_bug_report_dialog() -> BugReportDialog:
    """Create this page's dialog and register it for the client."""
    dialog = BugReportDialog()
    client_id = current_client_id()
    if client_id is not None:
        _dialogs[client_id] = dialog
    return dialog


def forget_dialog(client_id: str) -> None:
    """Drop a disconnected client's dialog."""
    _dialogs.pop(client_id, None)


async def open_bug_report_dialog() -> None:
    """Open the current page's report dialog, wherever it was triggered from."""
    client_id = current_client_id()
    dialog = _dialogs.get(client_id) if client_id is not None else None
    if dialog is None:
        ui.notify(t("bugreport.unavailable"), type="warning")
        return
    await dialog.open()
