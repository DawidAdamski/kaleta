"""Transactions view registration."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.transactions.page import transactions_page


def register() -> None:
    @ui.page("/transactions")
    async def _route(new: str = "") -> None:
        await transactions_page(open_new=new == "1")
