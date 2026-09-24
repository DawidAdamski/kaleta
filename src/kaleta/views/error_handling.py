# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map domain exceptions to NiceGUI user feedback.

A failure the user can act on gets more than a toast: when an event id was
issued, the error tray keeps it on screen with a "Report a problem" button,
so the path from "it broke" to a report the maintainer can read is one click
long instead of a trip to GitHub with an id copied by hand.
"""

from __future__ import annotations

import asyncio
from typing import Any

from nicegui import app, context, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.observability import SessionRingBuffer, set_session_resolver
from kaleta.services.event_capture import capture_exception_async
from kaleta.views.settings.user_prefs import get_events_enabled

#: asyncio holds only a weak reference to a task it did not await; without
#: this set a toast could be collected before it is shown.
_pending: set[asyncio.Task[None]] = set()
#: One tray per connected client; replaced whenever a page is built.
_trays: dict[str, ErrorTray] = {}
#: Event ids issued while this client was connected, newest last.
_client_event_ids: dict[str, list[str]] = {}
_MAX_TRACKED_EVENTS = 20


def current_client_id() -> str | None:
    """The NiceGUI client id, when called inside a client context."""
    # Before NiceGUI has started (startup handlers that log) there is no
    # client, and touching ``context.client`` would switch NiceGUI into script
    # mode with a request-less pseudo client that breaks its storage pruning.
    if not app.is_started:
        return None
    try:
        client = context.client
    except Exception:
        return None
    raw = getattr(client, "id", None)
    return str(raw) if raw else None


def session_event_ids(client_id: str | None = None) -> list[str]:
    """Event ids this session has seen — what a report offers to attach."""
    key = client_id or current_client_id()
    if key is None:
        return []
    return list(_client_event_ids.get(key, ()))


def record_event_id(event_id: str, client_id: str | None = None) -> None:
    key = client_id or current_client_id()
    if key is None:
        return
    seen = _client_event_ids.setdefault(key, [])
    if event_id not in seen:
        seen.append(event_id)
        del seen[:-_MAX_TRACKED_EVENTS]


def forget_client(client_id: str | None) -> None:
    """Drop everything held for a disconnected client."""
    if client_id is None:
        return
    from kaleta.views.bug_report_dialog import forget_dialog

    _trays.pop(client_id, None)
    _client_event_ids.pop(client_id, None)
    forget_dialog(client_id)
    SessionRingBuffer.drop(client_id)


class ErrorTray:
    """A dismissible strip carrying the message, the event id and Report."""

    def __init__(self) -> None:
        with (
            ui.element("div").classes(
                "k-error-tray fixed bottom-4 right-4 z-50 max-w-sm w-80"
            ) as self.root,
            ui.card().classes("w-full p-4 gap-2 shadow-lg"),
        ):
            with ui.row().classes("w-full items-start gap-2 flex-nowrap"):
                ui.icon("error", color="negative")
                self._message = ui.label("").classes("text-sm flex-grow")
                ui.button(icon="close", on_click=self.hide).props("flat dense round")
            with ui.row().classes("w-full items-center gap-2"):
                self._event = ui.label("").classes("k-mono text-xs text-slate-500")
                ui.space()
                ui.button(
                    t("bugreport.report_action"),
                    icon="bug_report",
                    on_click=self._open_report,
                ).props("flat dense color=primary")
        self.root.set_visibility(False)

    def show(self, message: str, event_id: str | None) -> None:
        self._message.set_text(message)
        self._event.set_text(t("bugreport.event_id_label", event_id=event_id) if event_id else "")
        self.root.set_visibility(True)

    def hide(self) -> None:
        self.root.set_visibility(False)

    async def _open_report(self) -> None:
        from kaleta.views.bug_report_dialog import open_bug_report_dialog

        self.hide()
        await open_bug_report_dialog()


def install_error_tray() -> ErrorTray:
    """Create this page's tray and register it for the client."""
    tray = ErrorTray()
    client_id = current_client_id()
    if client_id is not None:
        _trays[client_id] = tray
    return tray


def _current_tray() -> ErrorTray | None:
    client_id = current_client_id()
    return _trays.get(client_id) if client_id is not None else None


def install_session_resolver() -> None:
    """Teach the log ring buffer which session a NiceGUI event belongs to."""
    set_session_resolver(current_client_id)

    def _on_disconnect(client: Any) -> None:
        forget_client(str(getattr(client, "id", "")) or None)

    app.on_disconnect(_on_disconnect)


async def _notify_with_event(exc: KaletaError, client: Any | None) -> None:
    """Capture the failure, then speak to *client* — its slot, not this task's."""
    if client is None:
        await capture_exception_async(exc, user_events_enabled=None)
        return

    # NiceGUI keys the slot stack by asyncio task, and this coroutine runs in
    # a task of its own: without re-entering the client, every ui.* call here
    # would raise "the slot stack for this task is empty".
    with client:
        session_id = str(getattr(client, "id", "")) or None
        try:
            route: str | None = client.request.url.path
        except Exception:
            route = None

        user_id = app.storage.user.get(SESSION_USER_ID)
        event_id = await capture_exception_async(
            exc,
            route=route,
            session_id=session_id,
            user_id=user_id,
            user_events_enabled=get_events_enabled(),
        )
        message = exc.message
        if event_id:
            record_event_id(event_id, session_id)
            message = t("common.error_with_event_id", message=exc.message, event_id=event_id)

        tray = _trays.get(session_id) if session_id else None
        if tray is not None and event_id:
            # An event id means there is something to report — keep it on screen.
            tray.show(exc.message, event_id)
        ui.notify(message, type="negative", multi_line=True)


def notify_kaleta_error(exc: KaletaError) -> None:
    """Show a negative toast for a handled domain error."""
    client: Any | None
    try:
        client = context.client
    except Exception:
        client = None
    task = asyncio.create_task(_notify_with_event(exc, client))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def handle_kaleta_error(exc: Exception) -> bool:
    """Return True when *exc* is a :class:`KaletaError` and was shown to the user."""
    if isinstance(exc, KaletaError):
        notify_kaleta_error(exc)
        return True
    return False
