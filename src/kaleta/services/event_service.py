# SPDX-License-Identifier: AGPL-3.0-or-later
"""Capture and query anonymous application error events."""

from __future__ import annotations

import hashlib
import logging
import secrets
import traceback
from datetime import UTC, datetime, timedelta
from importlib.metadata import version as pkg_version
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.config import settings
from kaleta.models.app_event import AppEvent

logger = logging.getLogger(__name__)

_EVENT_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32-ish, no I/L/O
_MAX_STACK_CHARS = 8000
_MAX_EVENT_ID_ATTEMPTS = 5


def _app_version() -> str:
    try:
        return pkg_version("kaleta")
    except Exception:
        return "unknown"


def _generate_event_id() -> str:
    """Return an 8-character human-friendly event id."""
    return "".join(secrets.choice(_EVENT_ID_ALPHABET) for _ in range(8))


def extract_code_stack(exc: BaseException) -> str:
    """Keep traceback frames that originate under ``src/kaleta`` only."""
    if exc.__traceback__ is None:
        return "(no traceback)"
    frames = traceback.extract_tb(exc.__traceback__)
    lines: list[str] = []
    for frame in frames:
        if "/kaleta/" not in frame.filename:
            continue
        lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}')
        if frame.line:
            lines.append(f"    {frame.line}")
    if not lines:
        return "(no kaleta code frames)"
    text = "\n".join(lines)
    return text[:_MAX_STACK_CHARS]


def stack_hash(exc: BaseException) -> str:
    """Stable hash for grouping similar failures."""
    payload = f"{type(exc).__name__}:{extract_code_stack(exc)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def event_payload_fields(exc: BaseException) -> dict[str, Any]:
    """Public shape persisted for an event — unit-tested for no PII keys."""
    stack = extract_code_stack(exc)
    return {
        "level": "ERROR",
        "exception_class": type(exc).__name__,
        "stack_hash": stack_hash(exc),
        "stack_trace": stack,
        "app_version": _app_version(),
    }


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        exc: BaseException,
        *,
        route: str | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
        request_id: str | None = None,
    ) -> str:
        """Persist an anonymous error event and return its short ``event_id``."""
        fields = event_payload_fields(exc)
        for _ in range(_MAX_EVENT_ID_ATTEMPTS):
            event_id = _generate_event_id()
            existing = await self.session.scalar(
                select(AppEvent.id).where(AppEvent.event_id == event_id).limit(1)
            )
            if existing is None:
                break
        else:
            msg = "Could not allocate a unique event_id"
            raise RuntimeError(msg)

        row = AppEvent(
            event_id=event_id,
            occurred_at=datetime.now(UTC),
            route=route,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            **fields,
        )
        self.session.add(row)
        await self.session.commit()
        logger.info("Recorded app event %s (%s)", event_id, fields["exception_class"])
        return event_id

    async def get_by_event_id(self, event_id: str) -> AppEvent | None:
        result = await self.session.execute(
            select(AppEvent).where(AppEvent.event_id == event_id.upper()).limit(1)
        )
        return result.scalar_one_or_none()

    async def purge_older_than(self, days: int) -> int:
        if days < 1:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(AppEvent).where(AppEvent.occurred_at < cutoff)
        result = await self.session.execute(stmt.execution_options(synchronize_session=False))
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)


def instance_events_enabled() -> bool:
    return bool(settings.events_enabled)


def retention_days() -> int:
    return int(settings.event_retention_days)
