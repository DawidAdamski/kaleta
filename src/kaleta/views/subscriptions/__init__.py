# SPDX-License-Identifier: AGPL-3.0-or-later
"""Subscriptions wizard page."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.subscriptions.page import subscriptions_page


def register() -> None:
    @ui.page("/wizard/subscriptions")
    async def _route() -> None:
        await subscriptions_page()
