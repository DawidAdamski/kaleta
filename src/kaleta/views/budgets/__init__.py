# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budgets page."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.budgets.page import budgets_page


def register() -> None:
    @ui.page("/budgets")
    async def _route() -> None:
        await budgets_page()
