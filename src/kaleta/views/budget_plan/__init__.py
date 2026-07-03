"""Annual budget planning grid (/budget-plan)."""

from __future__ import annotations

from nicegui import ui

from kaleta.views.budget_plan.page import budget_plan_page


def register() -> None:
    @ui.page("/budget-plan")
    async def _route() -> None:
        await budget_plan_page()
