# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map domain exceptions to NiceGUI user feedback."""

from __future__ import annotations

import asyncio

from nicegui import app, ui

from kaleta.auth.session import SESSION_USER_ID
from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.services.event_capture import capture_exception_async
from kaleta.views.settings.user_prefs import get_events_enabled


async def _notify_with_event(exc: KaletaError) -> None:
    route: str | None = None
    session_id: str | None = None
    client = getattr(ui.context, "client", None)
    if client is not None:
        route = client.request.url.path
        raw_session = getattr(client, "id", None)
        session_id = str(raw_session) if raw_session else None

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
        message = t("common.error_with_event_id", message=exc.message, event_id=event_id)
    ui.notify(message, type="negative", multi_line=True)


def notify_kaleta_error(exc: KaletaError) -> None:
    """Show a negative toast for a handled domain error."""
    asyncio.create_task(_notify_with_event(exc))


def handle_kaleta_error(exc: Exception) -> bool:
    """Return True when *exc* is a :class:`KaletaError` and was shown to the user."""
    if isinstance(exc, KaletaError):
        notify_kaleta_error(exc)
        return True
    return False
