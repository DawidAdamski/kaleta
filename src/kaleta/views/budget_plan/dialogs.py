"""Budget plan edit dialogs — single cell, fill-all-months, yearly spread."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from inspect import isawaitable
from typing import Any

from nicegui import ui

from kaleta.i18n import t
from kaleta.schemas.budget import BudgetCreate
from kaleta.services import BudgetService, with_session
from kaleta.services.budget_service import category_yearly_total, per_month_from_yearly_total
from kaleta.views.budget_plan.constants import month_labels


class EditDialogs:
    """Cell, monthly, and yearly budget edit dialogs."""

    def __init__(
        self,
        state: dict[str, Any],
        *,
        on_saved: Callable[[], Awaitable[None] | None],
    ) -> None:
        self._state = state
        self._on_saved = on_saved
        self._build()

    def _build(self) -> None:
        with ui.dialog() as self.cell_dialog, ui.card().classes("w-72"):
            self.cell_title = ui.label("").classes("text-base font-bold mb-3")
            self.cell_amount = ui.number(t("budgets.amount_pln"), min=0, format="%.2f").classes(
                "w-full"
            )
            ui.label(t("budget_plan.set_zero_hint")).classes("text-xs text-grey-5 mt-1")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=self.cell_dialog.close).props("flat")
                ui.button(t("common.save"), on_click=self._save_cell).props("color=primary")
            ui.keyboard(
                on_key=lambda e: (
                    self._save_cell()
                    if e.key == "Enter" and e.action.keydown
                    else self.cell_dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

        with ui.dialog() as self.monthly_dialog, ui.card().classes("w-72"):
            self.monthly_title = ui.label("").classes("text-base font-bold mb-1")
            ui.label(t("budget_plan.set_all_hint")).classes("text-xs text-grey-5 mb-3")
            self.monthly_amount = ui.number(
                t("budget_plan.monthly_amount_pln"), min=0, format="%.2f"
            ).classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=self.monthly_dialog.close).props("flat")
                ui.button(t("budget_plan.apply_all"), on_click=self._save_monthly).props(
                    "color=primary"
                )
            ui.keyboard(
                on_key=lambda e: (
                    self._save_monthly()
                    if e.key == "Enter" and e.action.keydown
                    else self.monthly_dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

        with ui.dialog() as self.yearly_dialog, ui.card().classes("w-72"):
            self.yearly_title = ui.label("").classes("text-base font-bold mb-3")
            self.yearly_amount = ui.number(
                t("budget_plan.yearly_total"), min=0, format="%.2f"
            ).classes("w-full")
            self.yearly_preview = ui.label("").classes("text-xs text-grey-5 mt-1")
            self.yearly_amount.on_value_change(self._update_yearly_preview)

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(t("common.cancel"), on_click=self.yearly_dialog.close).props("flat")
                ui.button(t("budget_plan.distribute_evenly"), on_click=self._save_yearly).props(
                    "color=primary"
                )
            ui.keyboard(
                on_key=lambda e: (
                    self._save_yearly()
                    if e.key == "Enter" and e.action.keydown
                    else self.yearly_dialog.close()
                    if e.key == "Escape" and e.action.keydown
                    else None
                )
            )

    def open_cell(
        self,
        *,
        cat_id: int,
        month: int,
        cat_name: str,
        current: Decimal | None,
    ) -> None:
        self._state["cat_id"] = cat_id
        self._state["month"] = month
        edit_year: int = self._state["edit_year"]
        self.cell_title.set_text(f"{cat_name} — {month_labels()[month - 1]} {edit_year}")
        self.cell_amount.set_value(float(current) if current else 0)
        self.cell_dialog.open()

    def open_monthly(self, *, cat_id: int, cat_name: str, suggest: float) -> None:
        self._state["cat_id"] = cat_id
        self.monthly_title.set_text(cat_name)
        self.monthly_amount.set_value(round(suggest, 2))
        self.monthly_dialog.open()

    def open_yearly(
        self,
        *,
        cat_id: int,
        cat_name: str,
        budget_map: dict[tuple[int, int], Decimal],
    ) -> None:
        self._state["cat_id"] = cat_id
        total = category_yearly_total(budget_map, cat_id)
        self.yearly_title.set_text(cat_name)
        self.yearly_amount.set_value(float(total))
        self.yearly_preview.set_text(
            t("budget_plan.per_month_preview", amount=f"{float(total) / 12:,.2f}") if total else ""
        )
        self.yearly_dialog.open()

    def _update_yearly_preview(self, e: object) -> None:  # noqa: ARG002
        try:
            total_val = float(self.yearly_amount.value or 0)
            self.yearly_preview.set_text(
                t("budget_plan.per_month_preview", amount=f"{total_val / 12:,.2f}")
            )
        except (TypeError, ZeroDivisionError):
            self.yearly_preview.set_text("")

    async def _call_saved(self) -> None:
        result = self._on_saved()
        if isawaitable(result):
            await result

    async def _save_cell(self) -> None:
        amount = Decimal(str(self.cell_amount.value or 0))
        cat_id = int(self._state["cat_id"])
        month = int(self._state["month"])
        year: int = self._state["edit_year"]

        async def _persist(session: Any) -> None:
            svc = BudgetService(session)
            if amount > 0:
                await svc.upsert(
                    BudgetCreate(category_id=cat_id, amount=amount, month=month, year=year)
                )
            else:
                existing = await svc.get_by_category_period(cat_id, month, year)
                if existing:
                    await svc.delete(existing.id)

        await with_session(_persist)
        await self._call_saved()
        self.cell_dialog.close()

    async def _save_monthly(self) -> None:
        try:
            amount = Decimal(str(self.monthly_amount.value or 0))
        except InvalidOperation:
            ui.notify(t("budget_plan.invalid_amount"), type="negative")
            return
        if amount <= 0:
            ui.notify(t("budget_plan.amount_positive"), type="warning")
            return
        cat_id = int(self._state["cat_id"])
        year: int = self._state["edit_year"]

        async def _persist(session: Any) -> None:
            svc = BudgetService(session)
            for month in range(1, 13):
                await svc.upsert(
                    BudgetCreate(category_id=cat_id, amount=amount, month=month, year=year)
                )

        await with_session(_persist)
        ui.notify(t("budget_plan.monthly_set"), type="positive")
        await self._call_saved()
        self.monthly_dialog.close()

    async def _save_yearly(self) -> None:
        try:
            total = Decimal(str(self.yearly_amount.value or 0))
        except InvalidOperation:
            ui.notify(t("budget_plan.invalid_amount"), type="negative")
            return
        if total <= 0:
            ui.notify(t("budget_plan.amount_positive"), type="warning")
            return
        monthly = per_month_from_yearly_total(total)
        cat_id = int(self._state["cat_id"])
        year: int = self._state["edit_year"]

        async def _persist(session: Any) -> None:
            svc = BudgetService(session)
            for month in range(1, 13):
                await svc.upsert(
                    BudgetCreate(category_id=cat_id, amount=monthly, month=month, year=year)
                )

        await with_session(_persist)
        ui.notify(t("budget_plan.yearly_set", amount=f"{monthly:,.2f}"), type="positive")
        await self._call_saved()
        self.yearly_dialog.close()
