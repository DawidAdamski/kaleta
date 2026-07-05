# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan toolbar — year chips and copy-from-previous-month."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.services import BudgetService, with_session
from kaleta.views.budget_plan.constants import month_options


def render_toolbar(
    state: dict[str, Any],
    *,
    today: datetime.date,
    on_years_changed: Callable[[], None],
    on_copy_done: Callable[[], None],
) -> None:
    """Render year selector chips and copy-forward control."""
    available_years = list(range(today.year - 4, today.year + 2))

    def _toggle_year(year: int) -> None:
        if year in state["years"] and len(state["years"]) > 1:
            state["years"].discard(year)
        elif year not in state["years"]:
            state["years"].add(year)
        else:
            return
        if len(state["years"]) == 1:
            state["edit_year"] = next(iter(state["years"]))
        year_chips.refresh()
        on_years_changed()

    with ui.row().classes("w-full items-center gap-3 flex-wrap"):
        ui.label(t("budget_plan.title")).classes("text-2xl font-bold")
        ui.space()
        ui.label(t("budget_plan.years_label")).classes("text-sm text-slate-500")

        @ui.refreshable
        def year_chips() -> None:
            for year in available_years:
                active = year in state["years"]
                ui.button(
                    str(year),
                    on_click=lambda yr=year: _toggle_year(yr),
                ).props(f"rounded dense {'color=primary' if active else 'outline color=grey-6'}")

        year_chips()

    ui.label(t("budget_plan.help_text")).classes("text-sm text-slate-500")

    default_target = max(today.month, 2)
    copy_state: dict[str, Any] = {"target_month": default_target}

    async def _copy_from_prev() -> None:
        target_m: int = int(copy_state["target_month"])
        target_y: int = state["edit_year"]
        if target_m == 1:
            from_y, from_m = target_y - 1, 12
        else:
            from_y, from_m = target_y, target_m - 1

        async def _run(session: Any) -> int:
            return await BudgetService(session).copy_forward(from_y, from_m, target_y, target_m)

        written = await with_session(_run)
        if written == 0:
            ui.notify(t("budget_plan.copy_forward_nothing"), type="info")
        else:
            ui.notify(
                t("budget_plan.copy_forward_done", count=written),
                type="positive",
            )
        on_copy_done()

    with ui.row().classes("w-full items-center gap-2 flex-wrap"):
        ui.label(t("budget_plan.copy_forward_into")).classes("text-sm text-slate-500")
        month_select = (
            ui.select(
                options=month_options(),
                value=default_target,
            )
            .props("dense outlined")
            .classes("w-40")
        )

        def _on_month(e: Any) -> None:
            copy_state["target_month"] = int(e.args) if e.args else default_target

        month_select.on("update:model-value", _on_month)
        ui.button(
            t("budget_plan.copy_from"),
            icon="content_copy",
            on_click=_copy_from_prev,
        ).props("color=primary unelevated size=sm")
