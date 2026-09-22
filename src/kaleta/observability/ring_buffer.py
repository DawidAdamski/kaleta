# SPDX-License-Identifier: AGPL-3.0-or-later
"""The last few redacted log lines of a session, kept in memory for a report.

Nothing here is persisted: the deque lives with the process and is dropped
when the session disconnects, so a user who never files a report leaves no
trace behind.
"""

from __future__ import annotations

import logging
from collections import OrderedDict, deque
from datetime import UTC, datetime
from typing import Any

from kaleta.observability.context import current_session_id

#: Per session. A report attaches at most this many lines.
MAX_RECORDS = 200
#: Guard against an unbounded number of sessions on a long-lived process.
MAX_SESSIONS = 100


class SessionRingBuffer:
    """Process-wide store of ``session_id -> last MAX_RECORDS log lines``."""

    _buffers: OrderedDict[str, deque[dict[str, Any]]] = OrderedDict()

    @classmethod
    def append(cls, session_id: str, entry: dict[str, Any]) -> None:
        buffer = cls._buffers.get(session_id)
        if buffer is None:
            buffer = deque(maxlen=MAX_RECORDS)
            cls._buffers[session_id] = buffer
            while len(cls._buffers) > MAX_SESSIONS:
                cls._buffers.popitem(last=False)
        cls._buffers.move_to_end(session_id)
        buffer.append(entry)

    @classmethod
    def records(cls, session_id: str | None) -> list[dict[str, Any]]:
        if session_id is None:
            return []
        return list(cls._buffers.get(session_id, ()))

    @classmethod
    def drop(cls, session_id: str | None) -> None:
        """Forget a session's lines — called when its client disconnects."""
        if session_id is not None:
            cls._buffers.pop(session_id, None)

    @classmethod
    def clear(cls) -> None:
        cls._buffers.clear()


class RingBufferHandler(logging.Handler):
    """Copy every redacted record of a known session into its ring buffer."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level=level)

    def emit(self, record: logging.LogRecord) -> None:
        session_id = current_session_id()
        if session_id is None:
            return
        try:
            SessionRingBuffer.append(
                session_id,
                {
                    "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                },
            )
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)
