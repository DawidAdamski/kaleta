"""Unified import view — generic CSV and bank-specific profiles."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.import_view.page import import_page


def register() -> None:
    @ui.page("/import")
    async def _route() -> None:
        await import_page()
