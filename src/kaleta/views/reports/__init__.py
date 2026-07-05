# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report builder page."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.reports.page import reports_page


def register() -> None:
    @ui.page("/reports/builder")
    async def _route() -> None:
        await reports_page()
