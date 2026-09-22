# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strip secrets and personal data out of log records before they are written.

A log line can end up in a bug report, so it is redacted at the handler — the
only place every record passes through, whichever logger produced it.
"""

from __future__ import annotations

import logging
import re

#: Longer arguments are almost always a payload (audit-log JSON is the usual
#: offender), not a message — they are cut before the message is formatted.
MAX_ARG_CHARS = 200

REDACTED = "[redacted]"

# ``Authorization: Bearer <token>`` names the scheme between the key and the
# secret, so the scheme is consumed here — matching only the next word would
# redact "Bearer" and leave the token itself in the clear.
_AUTH_RE = re.compile(
    r"(?i)\b(?P<key>bearer|authorization|api[_-]?token|token|password|secret[_-]?key|secret)"
    r"\b\s*[:=]?\s*(?:bearer\s+)?(?P<value>[^\s,;'\"]+)"
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_QUERY_RE = re.compile(r"(?P<path>(?:https?://|/)[^\s?]*)\?[^\s]+")


def redact(text: str) -> str:
    """Mask query strings, bearer tokens and e-mail addresses in *text*.

    Query strings go first: a ``?token=…`` swallowed by the credential rule
    would leave the rest of the query in the clear.
    """
    masked = _QUERY_RE.sub(lambda m: f"{m.group('path')}?{REDACTED}", text)
    masked = _AUTH_RE.sub(lambda m: f"{m.group('key')} {REDACTED}", masked)
    return _EMAIL_RE.sub(REDACTED, masked)


def shorten(value: object) -> object:
    """Cut an over-long string argument down to :data:`MAX_ARG_CHARS`."""
    if isinstance(value, str) and len(value) > MAX_ARG_CHARS:
        return f"{value[:MAX_ARG_CHARS]}…[{len(value)} chars truncated]"
    return value


class RedactingFilter(logging.Filter):
    """Format, shorten and mask a record in place, once, before any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {key: shorten(value) for key, value in record.args.items()}
        elif record.args:
            record.args = tuple(shorten(value) for value in record.args)
        record.msg = redact(record.getMessage())
        record.args = ()
        return True
