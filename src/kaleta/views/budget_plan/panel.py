# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan editor as a reusable panel (toolbar + grid).

Hosted by the Budgets page's **Plan** tab (``views/budgets/page.py``). It is the
former ``/budget-plan`` page body with the ``page_layout`` wrapper removed — the
host page owns the chrome now; the panel owns only the planning toolbar and the
editable grid. Kept here so the grace-period ``/budget-plan`` redirect shim and
the tab share one implementation.
"""

from __future__ import annotations

import datetime
from typing import Any

from kaleta.views.budget_plan.dialogs import EditDialogs
from kaleta.views.budget_plan.grid import build_plan_grid
from kaleta.views.budget_plan.toolbar import render_toolbar


async def render_plan_panel() -> None:
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

    render_toolbar(
        state,
        today=today,
        on_years_changed=_refresh_grid,
        on_copy_done=_refresh_grid,
    )
    await plan_grid()
