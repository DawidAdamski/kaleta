# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget plan editor as a reusable panel (toolbar + grid).

Hosted by the Budgets page's **Plan** tab (``views/budgets/page.py``). It is the
former ``/budget-plan`` page body with the ``page_layout`` wrapper removed — the
host page owns the chrome now; the panel owns only the planning toolbar and the
editable grid. Kept here so the grace-period ``/budget-plan`` redirect shim and
the tab share one implementation.

The host page owns the month the whole page is looking at: it hands the panel
that period (:meth:`PlanPanel.set_period`), hears back when a year chip moves
the planned year (``on_edit_year_changed``), and asks it to put the cursor on
one category's month (:meth:`PlanPanel.focus_category`).
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable
from typing import Any

from nicegui import ui

from kaleta.views.budget_plan.dialogs import EditDialogs
from kaleta.views.budget_plan.grid import build_plan_grid, plan_cell_key
from kaleta.views.budget_plan.toolbar import render_toolbar

#: How long the focus script keeps looking for the cell: the Plan tab has to
#: become visible, and a period change may be redrawing the grid under it.
_FOCUS_ATTEMPTS = 60
_FOCUS_INTERVAL_MS = 50


class PlanPanel:
    """The planning toolbar and the annual grid, steered by the host page."""

    def __init__(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        on_edit_year_changed: Callable[[int], None] | None = None,
    ) -> None:
        today = datetime.date.today()
        edit_year = year if year is not None else today.year
        self._state: dict[str, Any] = {
            "years": {edit_year},
            "edit_year": edit_year,
            "focus_month": month if month is not None else today.month,
            "cat_id": None,
            "month": None,
        }
        self._today = today
        self._on_edit_year_changed = on_edit_year_changed
        self._grid: Any = None
        self._sync_toolbar: Callable[[], None] | None = None

    @property
    def edit_year(self) -> int:
        year: int = self._state["edit_year"]
        return year

    async def render(self) -> None:
        dialogs = EditDialogs(self._state, on_saved=self._refresh_grid)
        self._grid = build_plan_grid(self._state, dialogs, on_refresh=self._refresh_grid)
        self._sync_toolbar = render_toolbar(
            self._state,
            today=self._today,
            on_years_changed=self._years_changed,
            on_copy_done=self._refresh_grid,
        )
        await self._grid()

    def set_period(self, year: int, month: int) -> None:
        """Plan ``year`` and aim the copy-forward control at ``month``.

        Earlier years already ticked stay as reference rows under it; later
        ones go, since the planned year is always the latest one shown.
        """
        changed_year = year != self._state["edit_year"]
        self._state["years"] = {y for y in self._state["years"] if y < year} | {year}
        self._state["edit_year"] = year
        self._state["focus_month"] = month
        if self._sync_toolbar is not None:
            self._sync_toolbar()
        if changed_year:
            self._refresh_grid()

    def focus_category(self, category_id: int, month: int) -> None:
        """Put keyboard focus on one category's amount for ``month``.

        Focus, not the edit dialog: saving stays the user's explicit act —
        Enter on the focused cell opens the editor.
        """
        selector = f'[data-plan-cell="{plan_cell_key(category_id, month)}"]'
        ui.run_javascript(
            "(() => {"
            f"  const selector = {json.dumps(selector)};"
            f"  let left = {_FOCUS_ATTEMPTS};"
            "  const attempt = () => {"
            "    const el = document.querySelector(selector);"
            "    if (el && el.offsetParent !== null) {"
            "      el.scrollIntoView({block: 'center', inline: 'center'});"
            "      el.focus({preventScroll: true});"
            "      return;"
            "    }"
            f"    if (--left > 0) setTimeout(attempt, {_FOCUS_INTERVAL_MS});"
            "  };"
            "  attempt();"
            "})()"
        )

    def _refresh_grid(self) -> None:
        if self._grid is not None:
            self._grid.refresh()

    def _years_changed(self) -> None:
        self._refresh_grid()
        if self._on_edit_year_changed is not None:
            self._on_edit_year_changed(self._state["edit_year"])
