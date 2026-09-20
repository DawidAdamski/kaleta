# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budgets page — routing, layout, and section wiring."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import BudgetService, with_session
from kaleta.services.budget_service import date_range_for_key
from kaleta.views.budgets.dialogs import build_edit_dialog
from kaleta.views.budgets.helpers import range_label, range_options
from kaleta.views.budgets.overview import render_overview_content
from kaleta.views.budgets.realization import (
    render_realization_flat,
    render_realization_grouped,
    render_realization_stats,
)
from kaleta.views.layout import page_layout
from kaleta.views.settings.user_prefs import budget_period_for
from kaleta.views.theme import (
    BODY_MUTED,
    PAGE_CONTAINER,
    PAGE_EYEBROW,
    PAGE_GAP_22,
    PAGE_TITLE,
    SECTION_CARD,
    SEGMENT,
    SELECT_PILL_SQUARE,
    TAB_ROW,
    TABS,
    TITLE_ACTION_PRIMARY,
)


async def budgets_page() -> None:
    today = datetime.date.today()
    budget_year, budget_month = budget_period_for(today)
    current_range: dict[str, str] = {"key": "this_month"}
    realization_state: dict[str, Any] = {
        "year": budget_year,
        "month": budget_month,
        "group": "flat",
    }
    eyebrow: ui.label

    def _set_eyebrow(elapsed_pct: float | None) -> None:
        """ "July 2026 · 10% of the month elapsed" — artboard `2b`'s title line.

        The percentage is the same one every pace bar's tick stands at, so the
        page says once what each of forty rows would otherwise have to.
        """
        month_name = t(f"payment_calendar.month_{realization_state['month']}")
        period = f"{month_name} {realization_state['year']}"
        if elapsed_pct is None:
            eyebrow.set_text(period)
            return
        eyebrow.set_text(
            f"{period} · {t('budgets.realization.elapsed_hint', pct=f'{elapsed_pct:.0f}')}"
        )

    @ui.refreshable
    async def budget_content() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        start, end = date_range_for_key(current_range["key"])

        async def _load(session: Any) -> Any:
            return await BudgetService(session).range_summary(start, end)

        summaries = await with_session(_load)
        render_overview_content(summaries, is_dark=is_dark)

    _, open_edit_dialog = await build_edit_dialog(
        budget_year,
        budget_month,
        on_saved=budget_content.refresh,
    )

    @ui.refreshable
    async def realization_content() -> None:
        year = realization_state["year"]
        month = realization_state["month"]
        group = realization_state["group"]

        async def _load(session: Any) -> Any:
            return await BudgetService(session).realization_for_month(year, month)

        rows = await with_session(_load)

        if not rows:
            _set_eyebrow(None)
            with ui.card().classes(SECTION_CARD):
                ui.label(t("budgets.realization.no_rows")).classes(f"{BODY_MUTED} py-2")
                ui.button(
                    t("budgets.realization.create_budget"),
                    icon="add",
                    on_click=open_edit_dialog,
                ).props("color=primary unelevated").classes("mt-2")
            return

        _set_eyebrow(rows[0].elapsed_pct)
        # The month in four figures before the month in forty rows: artboard
        # `2b` opens with Planned, Actual, Remaining and Used, and the same
        # sums close the table at the bottom.
        render_realization_stats(rows)
        if group == "by_parent":
            render_realization_grouped(rows)
        else:
            render_realization_flat(rows)

    @ui.refreshable
    def _render_tab_controls() -> None:
        """Whatever the tab you are on is steered by, on the tab row itself.

        Two tabs ask two different questions — a date range on Overview, a
        month and a grouping on Realization — and the artboard has room for
        exactly one set beside the tabs.
        """
        if tabs.value == t("budgets.tab_overview"):

            def on_range_change(e: Any) -> None:
                current_range["key"] = e.value
                budget_content.refresh()

            ui.select(
                options=range_options(),
                value=current_range["key"],
                on_change=on_range_change,
            ).props("dense options-dense borderless dropdown-icon=expand_more").classes(
                f"{SELECT_PILL_SQUARE} w-44"
            )
            ui.label(range_label(current_range["key"])).classes(BODY_MUTED)
            return

        month_opts = {i: t(f"payment_calendar.month_{i}") for i in range(1, 13)}
        year_opts = {y: str(y) for y in range(today.year - 2, today.year + 3)}

        def on_month_change(e: Any) -> None:
            realization_state["month"] = int(e.value)
            realization_content.refresh()

        def on_year_change(e: Any) -> None:
            realization_state["year"] = int(e.value)
            realization_content.refresh()

        def on_group_change(e: Any) -> None:
            realization_state["group"] = e.value
            realization_content.refresh()

        ui.select(
            options=month_opts,
            value=realization_state["month"],
            on_change=on_month_change,
        ).props("dense options-dense borderless dropdown-icon=expand_more").classes(
            f"{SELECT_PILL_SQUARE} w-32"
        )
        ui.select(
            options=year_opts,
            value=realization_state["year"],
            on_change=on_year_change,
        ).props("dense options-dense borderless dropdown-icon=expand_more").classes(
            f"{SELECT_PILL_SQUARE} k-mono w-24"
        )
        ui.toggle(
            {
                "flat": t("budgets.realization.group_flat"),
                "by_parent": t("budgets.realization.group_by_parent"),
            },
            value=realization_state["group"],
            on_change=on_group_change,
        ).props("dense unelevated no-caps toggle-text-color=info").classes(SEGMENT)

    with page_layout(t("budgets.title"), wide=True, container=f"{PAGE_CONTAINER} {PAGE_GAP_22}"):
        with ui.row().classes("w-full items-end justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-0 min-w-0"):
                eyebrow = ui.label("").classes(PAGE_EYEBROW).props("data-page-eyebrow")
                ui.label(t("budgets.title")).classes(PAGE_TITLE)
            ui.button(
                t("budgets.edit"),
                icon="edit",
                on_click=open_edit_dialog,
                color=None,
            ).props("flat no-caps dense").classes(TITLE_ACTION_PRIMARY)

        # The two tabs and the screen's own controls share one line over one
        # rule, which is what artboard `2b` draws in place of a tab strip with
        # a second toolbar under it.
        with ui.row().classes(f"{TAB_ROW} w-full items-end gap-4 no-wrap"):
            with (
                ui.tabs()
                .props("dense no-caps align=left indicator-color=transparent")
                .classes(TABS) as tabs
            ):
                overview_tab = ui.tab(t("budgets.tab_overview"), icon="bar_chart")
                realization_tab = ui.tab(t("budgets.tab_realization"), icon="track_changes")
            ui.space()
            with ui.row().classes("items-center gap-2 pb-2 no-wrap"):
                _render_tab_controls()

        tabs.on_value_change(lambda _: _render_tab_controls.refresh())

        with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent p-0"):
            with ui.tab_panel(overview_tab).classes("p-0"):
                await budget_content()

            with ui.tab_panel(realization_tab).classes("p-0"):
                await realization_content()
