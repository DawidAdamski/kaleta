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
from kaleta.views.budgets.realization import render_realization_flat, render_realization_grouped
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING


async def budgets_page() -> None:
    today = datetime.date.today()
    current_range: dict[str, str] = {"key": "this_month"}
    realization_state: dict[str, Any] = {
        "year": today.year,
        "month": today.month,
        "group": "flat",
    }

    @ui.refreshable
    async def budget_content() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        start, end = date_range_for_key(current_range["key"])

        async def _load(session: Any) -> Any:
            return await BudgetService(session).range_summary(start, end)

        summaries = await with_session(_load)
        render_overview_content(summaries, is_dark=is_dark)

    _, open_edit_dialog = await build_edit_dialog(
        today,
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
            with ui.card().classes(SECTION_CARD):
                ui.label(t("budgets.realization.no_rows")).classes(f"{BODY_MUTED} py-2")
                ui.button(
                    t("budgets.realization.create_budget"),
                    icon="add",
                    on_click=open_edit_dialog,
                ).props("color=primary unelevated").classes("mt-2")
            return

        elapsed = rows[0].elapsed_pct
        with ui.card().classes(SECTION_CARD):
            with ui.row().classes("w-full items-center justify-between gap-3 mb-3"):
                ui.label(t("budgets.realization.title")).classes(SECTION_HEADING)
                ui.label(t("budgets.realization.elapsed_hint", pct=f"{elapsed:.0f}")).classes(
                    BODY_MUTED
                )

            if group == "by_parent":
                render_realization_grouped(rows)
            else:
                render_realization_flat(rows)

    with page_layout(t("budgets.title"), wide=True):
        with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
            ui.label(t("budgets.title")).classes(PAGE_TITLE)
            ui.button(
                t("budgets.edit"),
                icon="edit",
                on_click=open_edit_dialog,
            ).props("color=primary")

        with ui.tabs().classes("w-full") as tabs:
            overview_tab = ui.tab(t("budgets.tab_overview"), icon="bar_chart")
            realization_tab = ui.tab(t("budgets.tab_realization"), icon="track_changes")

        with ui.tab_panels(tabs, value=overview_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(overview_tab):
                with ui.row().classes("w-full items-center gap-3 flex-wrap mb-2"):
                    range_date_label = ui.label(range_label("this_month")).classes(BODY_MUTED)

                    def on_range_change(e: Any) -> None:
                        current_range["key"] = e.value
                        range_date_label.set_text(range_label(e.value))
                        budget_content.refresh()

                    ui.select(
                        options=range_options(),
                        value="this_month",
                        label=t("budgets.period"),
                        on_change=on_range_change,
                    ).classes("w-44")

                await budget_content()

            with ui.tab_panel(realization_tab):
                with ui.row().classes("w-full items-center gap-3 flex-wrap mb-2"):
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
                        value=today.month,
                        on_change=on_month_change,
                    ).classes("w-40").props("dense outlined")
                    ui.select(
                        options=year_opts,
                        value=today.year,
                        on_change=on_year_change,
                    ).classes("w-28").props("dense outlined")
                    ui.space()
                    ui.toggle(
                        {
                            "flat": t("budgets.realization.group_flat"),
                            "by_parent": t("budgets.realization.group_by_parent"),
                        },
                        value="flat",
                        on_change=on_group_change,
                    ).props("dense unelevated")

                await realization_content()
