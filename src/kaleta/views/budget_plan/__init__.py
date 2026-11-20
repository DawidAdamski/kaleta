# SPDX-License-Identifier: AGPL-3.0-or-later
"""Annual budget planning grid — now a tab on the Budgets page.

``/budget-plan`` is kept for one release as a 302 redirect onto
``/budgets?tab=plan``, where the planning editor now lives (see
``views/budget_plan/panel.py``). The route is removed in a follow-up slice.
"""

from __future__ import annotations

from fastapi import status
from fastapi.responses import RedirectResponse
from nicegui import ui

#: Where the old planning address lands now.
PLAN_TAB_URL = "/budgets?tab=plan"


def plan_redirect() -> RedirectResponse:
    """The grace-period shim: a 302, so nothing caches the move as permanent.

    ``RedirectResponse`` defaults to 307; the plan promises a 302 for the one
    release the old address lives on.
    """
    return RedirectResponse(PLAN_TAB_URL, status_code=status.HTTP_302_FOUND)


def register() -> None:
    @ui.page("/budget-plan")
    def _route() -> RedirectResponse:
        return plan_redirect()
