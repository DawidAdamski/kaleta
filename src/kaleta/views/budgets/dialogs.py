# SPDX-License-Identifier: AGPL-3.0-or-later
"""Budget edit dialog for the current month."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.budget import BudgetCreate
from kaleta.services import BudgetService, CategoryService, with_session
from kaleta.views.theme import BODY_MUTED


async def build_edit_dialog(
    today: datetime.date,
    *,
    on_saved: Callable[[], Any],
) -> tuple[Any, Callable[[], Awaitable[None]]]:
    with ui.dialog() as edit_dialog, ui.card().classes("w-96"):
        ui.label(t("budgets.edit")).classes("text-lg font-bold")
        ui.label(
            t("budgets.period_label", month=f"{today.month:02d}", year=str(today.year))
        ).classes(f"{BODY_MUTED} mb-2")

        @ui.refreshable
        async def dialog_content() -> None:
            async def _load(session: Any) -> tuple[Any, ...]:
                month_summaries = await BudgetService(session).monthly_summary(
                    today.month, today.year
                )
                all_cats = await CategoryService(session).list()
                return month_summaries, all_cats

            month_summaries, all_cats = await with_session(_load)
            expense_cats = [c for c in all_cats if c.type.value == "expense"]
            budgeted_ids = {s.category_id for s in month_summaries}
            expense_cat_opts = CategoryService.build_option_labels(expense_cats)
            available = {k: v for k, v in expense_cat_opts.items() if k not in budgeted_ids}

            if available:
                ui.label(t("budgets.add_category_budget")).classes("text-sm font-medium mt-2")
                new_cat_sel = ui.select(available, label=t("common.category")).classes("w-full")
                new_cat_sel.value = next(iter(available))
                new_amount = ui.number(t("budgets.amount_pln"), min=1, format="%.2f").classes(
                    "w-full"
                )

                async def save_new() -> None:
                    if not new_cat_sel.value or not new_amount.value:
                        ui.notify(t("budgets.fill_all_fields"), type="negative")
                        return
                    data = BudgetCreate(
                        category_id=new_cat_sel.value,
                        amount=Decimal(str(new_amount.value)),
                        month=today.month,
                        year=today.year,
                    )

                    async def _upsert(session: Any) -> None:
                        await BudgetService(session).upsert(data)

                    await with_session(_upsert)
                    ui.notify(t("budgets.saved"), type="positive")
                    edit_dialog.close()
                    on_saved()

                ui.button(t("common.save"), on_click=save_new).props("color=primary").classes(
                    "mt-2"
                )
            else:
                ui.label(t("budgets.all_budgeted")).classes(BODY_MUTED)

            if month_summaries:
                ui.separator().classes("my-3")
                ui.label(t("budgets.edit_existing")).classes("text-sm font-medium")
                for summary in month_summaries:
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label(summary.category_name).classes("flex-1 text-sm")
                        amount_field = (
                            ui.number(value=float(summary.budget_amount), format="%.2f", min=0)
                            .classes("w-32")
                            .props("dense")
                        )

                        async def update_budget(
                            cat_id: int = summary.category_id,
                            field: ui.number = amount_field,
                        ) -> None:
                            data = BudgetCreate(
                                category_id=cat_id,
                                amount=Decimal(str(field.value or 0)),
                                month=today.month,
                                year=today.year,
                            )

                            async def _upsert(session: Any) -> None:
                                await BudgetService(session).upsert(data)

                            await with_session(_upsert)
                            ui.notify(t("budgets.saved"), type="positive")
                            edit_dialog.close()
                            on_saved()

                        ui.button(icon="save", on_click=update_budget).props("flat dense round")

        await dialog_content()
        with ui.row().classes("w-full justify-end mt-4"):
            ui.button(t("common.close"), on_click=edit_dialog.close).props("flat")

    async def open_edit_dialog() -> None:
        dialog_content.refresh()
        edit_dialog.open()

    return edit_dialog, open_edit_dialog
