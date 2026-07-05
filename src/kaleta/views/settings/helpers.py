# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared helpers for settings tab modules."""

from __future__ import annotations

from nicegui import app, ui

from kaleta.i18n import t


def set_user_key(key: str, value: object) -> None:
    """Persist a value to ``app.storage.user`` and toast confirmation."""
    app.storage.user[key] = value
    ui.notify(t("settings.saved"), type="positive")


def about_row(label: str, value: str) -> None:
    with ui.row().classes("w-full items-center gap-3"):
        ui.label(label).classes("text-sm text-slate-500 w-32")
        ui.label(value).classes("text-sm font-mono")
