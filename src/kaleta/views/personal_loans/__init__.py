"""Personal loans wizard page."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.personal_loans.page import personal_loans_page


def register() -> None:
    @ui.page("/wizard/personal-loans")
    async def _route() -> None:
        await personal_loans_page()
