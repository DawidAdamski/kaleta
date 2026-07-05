# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings page — tabbed structure with per-feature knobs."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.settings.page import settings_page


def register() -> None:
    @ui.page("/settings")
    async def _route() -> None:
        await settings_page()
