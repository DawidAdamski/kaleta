# SPDX-License-Identifier: AGPL-3.0-or-later
"""Annual budget planning grid — now a tab on the Budgets page.

``/budget-plan`` is kept for one release as a 302 redirect onto
``/budgets?tab=plan``, where the planning editor now lives (see
``views/budget_plan/panel.py``). The route is removed in a follow-up slice.
"""

from __future__ import annotations

from fastapi.responses import RedirectResponse
from nicegui import ui


def register() -> None:
    @ui.page("/budget-plan")
    def _route() -> RedirectResponse:
        return RedirectResponse("/budgets?tab=plan")
