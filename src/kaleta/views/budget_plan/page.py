# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan page — routing, layout, and section wiring."""

from __future__ import annotations

import datetime
from typing import Any

from kaleta.i18n import t
from kaleta.views.budget_plan.dialogs import EditDialogs
from kaleta.views.budget_plan.grid import build_plan_grid
from kaleta.views.budget_plan.toolbar import render_toolbar
from kaleta.views.layout import page_layout


async def budget_plan_page() -> None:
    today = datetime.date.today()
    state: dict[str, Any] = {
        "years": {today.year},
        "edit_year": today.year,
        "cat_id": None,
        "month": None,
    }

    plan_grid_ref: dict[str, Any] = {}

    def _refresh_grid() -> None:
        plan_grid = plan_grid_ref.get("plan_grid")
        if plan_grid is not None:
            plan_grid.refresh()

    dialogs = EditDialogs(state, on_saved=_refresh_grid)
    plan_grid = build_plan_grid(state, dialogs, on_refresh=_refresh_grid)
    plan_grid_ref["plan_grid"] = plan_grid

    with page_layout(t("budget_plan.title")):
        render_toolbar(
            state,
            today=today,
            on_years_changed=_refresh_grid,
            on_copy_done=_refresh_grid,
        )
        await plan_grid()
