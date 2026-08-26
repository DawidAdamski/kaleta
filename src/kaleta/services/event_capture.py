# SPDX-License-Identifier: AGPL-3.0-or-later
"""Best-effort anonymous error capture from UI and API paths."""

from __future__ import annotations

import logging
from typing import Any

from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import KaletaError, kaleta_error_http_status
from kaleta.services.event_service import EventService, instance_events_enabled

logger = logging.getLogger(__name__)


def _should_capture(exc: Exception, *, user_events_enabled: bool | None) -> bool:
    if not instance_events_enabled():
        return False
    if user_events_enabled is False:
        return False
    if isinstance(exc, KaletaError):
        return kaleta_error_http_status(exc) >= 500
    return True


async def capture_exception_async(
    exc: Exception,
    *,
    route: str | None = None,
    session_id: str | None = None,
    user_id: int | None = None,
    request_id: str | None = None,
    user_events_enabled: bool | None = None,
) -> str | None:
    """Record an error event when enabled; swallow persistence failures."""
    if not _should_capture(exc, user_events_enabled=user_events_enabled):
        return None
    try:
        async with AsyncSessionFactory() as session:
            return await EventService(session).record(
                exc,
                route=route,
                session_id=session_id,
                user_id=user_id,
                request_id=request_id,
            )
    except Exception:
        logger.exception("Failed to capture app event")
        return None


def capture_exception_sync(**kwargs: Any) -> None:
    """Schedule capture from a sync UI handler when an event loop is running."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(capture_exception_async(**kwargs))
        return
    loop.create_task(capture_exception_async(**kwargs))
