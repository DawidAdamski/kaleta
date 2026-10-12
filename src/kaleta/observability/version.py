# SPDX-License-Identifier: AGPL-3.0-or-later
"""The version string that goes on every event, report and log line."""

from __future__ import annotations


def app_version() -> str:
    """The app version — git-derived by hatch-vcs, resolved once in ``kaleta``.

    One source of truth with ``kaleta.__version__`` (read from the installed
    package metadata); ``"unknown"`` if that is unavailable.
    """
    try:
        from kaleta import __version__

        return __version__
    except Exception:
        return "unknown"
