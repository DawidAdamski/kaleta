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
from kaleta.views.theme import (
    BUTTON_INK,
    MUTED,
    MUTED_STRONG,
    PAGE_EYEBROW,
    PAGE_TITLE,
    SELECT_PILL_SQUARE,
    YEAR_CHIP,
    YEAR_CHIP_ON,
)


def render_toolbar(
    state: dict[str, Any],
    *,
    today: datetime.date,
    on_years_changed: Callable[[], None],
    on_copy_done: Callable[[], None],
) -> Callable[[], None]:
    """Render year selector chips and copy-forward control.

    Returns a callback that redraws both from ``state`` — the host page calls
    it after moving the planned year or month from its own selector.
    """
    base_years = set(range(today.year - 4, today.year + 2))

    def _available_years() -> list[int]:
        # The page's year selector reaches a year further out than the chips
        # do; a planned year always has a chip, so it can be seen and unticked.
        return sorted(base_years | state["years"])

    def _toggle_year(year: int) -> None:
        if year in state["years"] and len(state["years"]) > 1:
            state["years"].discard(year)
        elif year not in state["years"]:
            state["years"].add(year)
        else:
            return
        # The latest chosen year is the one being planned; any earlier ones
        # add their actuals under it as reference rows.
        state["edit_year"] = max(state["years"])
        year_chips.refresh()
        on_years_changed()

    with ui.row().classes("w-full items-end justify-between gap-6 no-wrap"):
        with ui.column().classes("gap-0 min-w-0 shrink"):
            # The help line is the eyebrow: it says what the grid under it
            # responds to, which is exactly what artboard `2c` puts there.
            ui.label(t("budget_plan.help_text")).classes(PAGE_EYEBROW).props(
                "data-page-eyebrow"
            ).tooltip(t("budget_plan.help_text_more"))
            ui.label(t("budget_plan.title")).classes(PAGE_TITLE)
        with ui.row().classes("items-center gap-3.5 no-wrap"):
            ui.label(t("budget_plan.years_label")).classes(f"{MUTED_STRONG} text-[11.5px]")

            @ui.refreshable
            def year_chips() -> None:
                with ui.row().classes("gap-1.5 no-wrap"):
                    for year in _available_years():
                        active = year in state["years"]
                        ui.button(
                            str(year),
                            on_click=lambda yr=year: _toggle_year(yr),
                            color=None,
                        ).props("flat dense no-caps").classes(YEAR_CHIP_ON if active else YEAR_CHIP)

            year_chips()

    def _target_for(month: int) -> int:
        # January has no previous month inside the planned year to copy from.
        return max(month, 2)

    default_target = _target_for(int(state.get("focus_month", today.month)))
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

    with ui.row().classes("w-full items-center gap-2.5 flex-wrap"):
        ui.label(t("budget_plan.copy_forward_into")).classes(f"{MUTED} text-[12px]")
        month_select = (
            ui.select(
                options=month_options(),
                value=default_target,
            )
            .props("dense options-dense borderless dropdown-icon=expand_more")
            .classes(f"{SELECT_PILL_SQUARE} w-36")
        )

        def _on_month(e: Any) -> None:
            copy_state["target_month"] = int(e.args) if e.args else copy_state["target_month"]

        month_select.on("update:model-value", _on_month)
        ui.button(
            t("budget_plan.copy_from"),
            icon="content_copy",
            on_click=_copy_from_prev,
            color=None,
        ).props("flat dense no-caps").classes(BUTTON_INK)

    def _sync() -> None:
        year_chips.refresh()
        target = _target_for(int(state.get("focus_month", today.month)))
        copy_state["target_month"] = target
        month_select.set_value(target)

    return _sync
