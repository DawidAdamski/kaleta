# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application-wide logging configuration.

``KALETA_LOG_FORMAT=json`` turns every line into one JSON object carrying the
correlation fields from :mod:`kaleta.observability.context`, so an event id
shown to a user leads straight to the lines around it. Records are redacted
and copied into the session ring buffer on their way out.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import Headers, MutableHeaders

from kaleta.config import settings
from kaleta.observability import (
    RedactingFilter,
    RingBufferHandler,
    app_version,
    bind_request,
    context_fields,
    new_request_id,
    redact,
    reset,
)

log = logging.getLogger(__name__)

TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


class JsonFormatter(logging.Formatter):
    """One JSON object per record, with the request correlation fields."""

    def __init__(self, *, app_version_override: str | None = None) -> None:
        super().__init__()
        self.app_version = app_version_override or app_version()

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "app_version": self.app_version,
        }
        payload.update(context_fields())
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def _resolved_level() -> int:
    if settings.debug:
        return logging.DEBUG
    return logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)


def configure_logging() -> None:
    """Configure root logging; honour ``KALETA_LOG_FORMAT`` and ``KALETA_DEBUG``."""
    level = _resolved_level()

    stream = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        stream.setFormatter(JsonFormatter())
    else:
        stream.setFormatter(logging.Formatter(TEXT_FORMAT))

    ring = RingBufferHandler(level=max(level, logging.INFO))

    redacting = RedactingFilter()
    for handler in (stream, ring):
        handler.addFilter(redacting)

    logging.basicConfig(level=level, handlers=[stream, ring], force=True)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


class RequestContextMiddleware:
    """Bind a correlation context around every HTTP request.

    Accepts an incoming ``X-Request-ID``, generates one otherwise, and returns
    it on the response. With ``access_log`` it also logs method, path, status
    and duration — the access line API mode has always written.
    """

    def __init__(self, app: Any, *, access_log: bool = False) -> None:
        self.app = app
        self.access_log = access_log

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        request_id = incoming or new_request_id()
        tokens = bind_request(request_id=request_id, route=scope.get("path"))
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        def _access_line() -> None:
            if not self.access_log:
                return
            log.info(
                "%s %s -> %s (%.1f ms)",
                scope.get("method", "?"),
                scope.get("path", "?"),
                status_code,
                (time.perf_counter() - start) * 1000,
            )

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            # Starlette's 500 handler runs *outside* this middleware, so the
            # context stays bound on the way out — otherwise the event id it
            # issues and the lines around it would lose their request id. The
            # binding dies with the request task, and every bind_request sets
            # all six values, so a later request can never read a stale one.
            _access_line()
            raise
        _access_line()
        reset(tokens)
