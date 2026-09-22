# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional Sentry-protocol forwarding of the anonymous event, behind a flag.

``KALETA_ERROR_TRACKER_DSN`` points at a self-hosted GlitchTip (or Sentry).
Default off, and an outgoing event is cut down to exactly the fields the
anonymous ``app_events`` row already holds — nothing about the ledger, the
request body or the user leaves the instance.
"""

from __future__ import annotations

import logging
from typing import Any

from kaleta.config import settings
from kaleta.observability import app_version, current_event_id, current_route, redact

logger = logging.getLogger(__name__)

#: Everything else is dropped by :func:`scrub_event` before it is sent.
ALLOWED_KEYS = frozenset(
    {"event_id", "exception", "level", "logger", "platform", "release", "tags", "timestamp"}
)
ALLOWED_TAGS = frozenset({"route", "kaleta_event_id"})


def tracker_dsn() -> str | None:
    return settings.error_tracker_dsn or None


def _scrub_exception(exception: Any) -> Any:
    """Keep the exception type and redacted frames; drop values and locals."""
    if not isinstance(exception, dict):
        return exception
    values = exception.get("values")
    if not isinstance(values, list):
        return exception
    scrubbed = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        item: dict[str, Any] = {"type": entry.get("type")}
        if isinstance(entry.get("value"), str):
            item["value"] = redact(entry["value"])
        stacktrace = entry.get("stacktrace")
        if isinstance(stacktrace, dict) and isinstance(stacktrace.get("frames"), list):
            item["stacktrace"] = {
                "frames": [
                    {
                        "filename": frame.get("filename"),
                        "lineno": frame.get("lineno"),
                        "function": frame.get("function"),
                    }
                    for frame in stacktrace["frames"]
                    if isinstance(frame, dict)
                ]
            }
        scrubbed.append(item)
    return {"values": scrubbed}


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """``before_send`` — strip the event down to the anonymous fields."""
    scrubbed = {key: value for key, value in event.items() if key in ALLOWED_KEYS}
    if "exception" in scrubbed:
        scrubbed["exception"] = _scrub_exception(scrubbed["exception"])
    tags = scrubbed.get("tags")
    scrubbed["tags"] = (
        {key: value for key, value in tags.items() if key in ALLOWED_TAGS}
        if isinstance(tags, dict)
        else {}
    )
    scrubbed["release"] = app_version()
    return scrubbed


def init_error_tracker() -> bool:
    """Initialise the tracker when a DSN is configured; ``False`` otherwise."""
    dsn = tracker_dsn()
    if not dsn:
        return False
    try:
        import sentry_sdk  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        logger.warning(
            "KALETA_ERROR_TRACKER_DSN is set but sentry-sdk is missing "
            "— install the 'tracker' extra"
        )
        return False
    sentry_sdk.init(
        dsn=dsn,
        release=app_version(),
        send_default_pii=False,
        max_request_body_size="never",
        before_send=scrub_event,
    )
    logger.info("Error tracker enabled (release=%s)", app_version())
    return True


def forward_exception(exc: BaseException, *, event_id: str | None = None) -> None:
    """Forward an already-captured error; never raise into the caller."""
    if not tracker_dsn():
        return
    try:
        import sentry_sdk  # type: ignore[import-not-found,unused-ignore]

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("route", current_route() or "?")
            scope.set_tag("kaleta_event_id", event_id or current_event_id() or "?")
            sentry_sdk.capture_exception(exc)
    except Exception:
        logger.exception("Error tracker forwarding failed")
