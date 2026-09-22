# SPDX-License-Identifier: AGPL-3.0-or-later
"""The version string that goes on every event, report and log line."""

from __future__ import annotations

from importlib.metadata import version as pkg_version


def app_version() -> str:
    """Installed package version, or ``"unknown"`` outside an installed tree."""
    try:
        return pkg_version("kaleta")
    except Exception:
        return "unknown"
