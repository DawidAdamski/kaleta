# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the About tab shows a user who is about to file an issue.

The panel exists so a self-hoster can answer "what is your setup?" without
being walked through a dozen questions: versions, the configuration actually
in force, the keys their session holds, and the last few log lines.

Everything here is assembled with one rule: **a secret never reaches the
output.** A value is masked by the name it is stored under, not by looking at
it, so a key added to ``Settings`` later is redacted by default rather than
leaking until someone notices. The log lines come from the session ring
buffer, which has already been through :func:`kaleta.observability.redact`.

The module is deliberately free of NiceGUI: what the session holds is handed
in by the view, so the whole report can be built and asserted on in a test.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from kaleta.config import settings
from kaleta.observability import SessionRingBuffer, app_version, current_session_id

__all__ = [
    "MASK",
    "DebugSection",
    "build_sections",
    "env_rows",
    "mask_db_url",
    "mask_env_value",
    "sections_as_markdown",
    "version_rows",
]

#: What stands in for a value that must not be shown.
MASK = "***"

#: How many log lines the panel shows, newest last.
LOG_TAIL_LINES = 30

#: A ``KALETA_*`` name holding any of these is printed as :data:`MASK`.
#: Substrings, not exact names — ``KALETA_SMTP_PASSWORD`` and a
#: ``KALETA_..._WEBHOOK`` added next year are both covered without an edit.
_SECRET_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "KEY",
    "DSN",
    "WEBHOOK",
)

#: Packages whose versions decide how a bug reproduces.
_REPORTED_PACKAGES = ("nicegui", "fastapi", "sqlalchemy", "pydantic", "alembic")


@dataclass(frozen=True, slots=True)
class DebugSection:
    """One titled block of ``label: value`` rows, or free-form ``lines``."""

    title: str
    rows: list[tuple[str, str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    empty_note: str = ""


def mask_db_url(url: str) -> str:
    """The database URL with the password taken out, host and name kept.

    ``postgresql+asyncpg://kaleta:s3cret@db:5432/kaleta`` becomes
    ``postgresql+asyncpg://kaleta:***@db:5432/kaleta``. A SQLite URL has no
    credentials and comes back untouched.
    """
    scheme, sep, remainder = url.partition("://")
    if not sep or "@" not in remainder:
        return url
    credentials, _, host_part = remainder.rpartition("@")
    user, colon, _password = credentials.partition(":")
    if not colon:
        return url
    return f"{scheme}://{user}:{MASK}@{host_part}"


def mask_env_value(name: str, value: str) -> str:
    """The value as it may be printed, given the name it is stored under."""
    upper = name.upper()
    if any(marker in upper for marker in _SECRET_MARKERS):
        return MASK if value else ""
    if upper.endswith("DB_URL") or upper.endswith("MIGRATE_URL"):
        return mask_db_url(value)
    return value


def version_rows() -> list[tuple[str, str]]:
    """Kaleta, Python, the platform and the libraries that shape behaviour."""
    rows = [
        ("Kaleta", app_version()),
        ("Python", sys.version.split()[0]),
        ("Platform", f"{platform.system()} {platform.release()} ({platform.machine()})"),
    ]
    for name in _REPORTED_PACKAGES:
        try:
            rows.append((name, pkg_version(name)))
        except PackageNotFoundError:  # pragma: no cover - always installed here
            rows.append((name, "not installed"))
    return rows


def env_rows(environ: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Every ``KALETA_*`` variable actually set, values masked by name.

    Only what the operator set is listed. Printing the defaults too would bury
    the three lines that explain the bug in forty that do not.
    """
    source = os.environ if environ is None else environ
    return [
        (name, mask_env_value(name, source[name]))
        for name in sorted(source)
        if name.startswith("KALETA_")
    ]


def _settings_rows() -> list[tuple[str, str]]:
    """The configuration in force, defaults included — masked the same way."""
    rows: list[tuple[str, str]] = []
    for name, value in sorted(settings.model_dump().items()):
        rows.append((name, mask_env_value(name, "" if value is None else str(value))))
    return rows


def _log_lines() -> list[str]:
    records = SessionRingBuffer.records(current_session_id())
    return [
        f"{record.get('ts', '')} {record.get('level', '')} [{record.get('logger', '')}] "
        f"{record.get('msg', '')}"
        for record in records[-LOG_TAIL_LINES:]
    ]


def build_sections(
    *,
    storage_keys: dict[str, str] | None = None,
    feature_flags: dict[str, str] | None = None,
) -> list[DebugSection]:
    """The whole report.

    ``storage_keys`` maps a ``app.storage.user`` key to the *type* of what is
    stored under it — never the value. A session holds a default account id and
    a language, but it also holds whatever a later feature puts there, and the
    panel is not the place to find out which.
    """
    sections = [
        DebugSection(title="Versions", rows=version_rows()),
        DebugSection(
            title="Environment",
            rows=env_rows(),
            empty_note="No KALETA_* variables set — every setting is at its default.",
        ),
        DebugSection(title="Settings in force", rows=_settings_rows()),
        DebugSection(
            title="Session storage keys",
            rows=sorted((storage_keys or {}).items()),
            empty_note="This session holds no stored preferences yet.",
        ),
        DebugSection(
            title="Feature settings",
            rows=sorted((feature_flags or {}).items()),
            empty_note="No feature settings were read.",
        ),
        DebugSection(
            title=f"Recent log lines (last {LOG_TAIL_LINES})",
            lines=_log_lines(),
            empty_note="No log lines were captured for this session.",
        ),
    ]
    return sections


def sections_as_markdown(sections: list[DebugSection]) -> str:
    """The report as a Markdown block, ready to paste into a GitHub issue.

    Markdown rather than JSON: the destination is an issue body, where a table
    renders and a JSON blob has to be unfolded by whoever reads it.
    """
    parts: list[str] = ["## Kaleta debug info", ""]
    for section in sections:
        parts.append(f"### {section.title}")
        parts.append("")
        if section.rows:
            parts.append("| Key | Value |")
            parts.append("| --- | --- |")
            parts.extend(f"| {key} | `{value}` |" for key, value in section.rows)
        elif section.lines:
            parts.append("```")
            parts.extend(section.lines)
            parts.append("```")
        else:
            parts.append(f"_{section.empty_note}_")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
