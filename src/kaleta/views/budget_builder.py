from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from nicegui import ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.category import CategoryType
from kaleta.schemas.yearly_plan import (
    FixedLine,
    IncomeLine,
    VariableLine,
    YearlyPlanPayload,
)
from kaleta.services import CategoryService, YearlyPlanService
from kaleta.views.layout import page_layout
from kaleta.views.theme import BODY_MUTED, PAGE_TITLE, SECTION_CARD, SECTION_HEADING


def _fmt(d: Decimal) -> str:
    return f"{d:,.2f}"


def register() -> None:
    @ui.page("/wizard/budget-builder")
    async def budget_builder_page() -> None:
        today = datetime.date.today()
        current_year = today.year

        async with AsyncSessionFactory() as session:
            payload = await YearlyPlanService(session).get_payload(current_year)
            expense_cats = await CategoryService(session).list(type=CategoryType.EXPENSE)

        cat_opts: dict[int, str] = {c.id: c.name for c in expense_cats}

        # Local mutable state — always in sync with the form inputs
        state: dict[str, Any] = {
            "year": current_year,
            "income": [line.model_copy() for line in payload.income_lines],
            "fixed": [line.model_copy() for line in payload.fixed_lines],
            "variable": [line.model_copy() for line in payload.variable_lines],
        }

        def _current_payload() -> YearlyPlanPayload:
            return YearlyPlanPayload(
                year=state["year"],
                income_lines=state["income"],
                fixed_lines=state["fixed"],
                variable_lines=state["variable"],
            )

        with page_layout(t("budget_builder.title"), wide=True):
            # ── Header ───────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(t("budget_builder.title")).classes(PAGE_TITLE)
                    ui.label(t("budget_builder.subtitle")).classes(BODY_MUTED)
                with ui.row().classes("items-center gap-2"):
                    ui.icon("event", size="1.2rem").classes("text-primary")
                    ui.label(str(current_year)).classes("text-xl font-semibold text-primary")

            # ── Income section ───────────────────────────────────────────
            income_col: ui.column
            fixed_col: ui.column
            variable_col: ui.column

            def _render_income() -> None:
                income_col.clear()
                with income_col:
                    if not state["income"]:
                        ui.label(t("budget_builder.income_empty")).classes(f"{BODY_MUTED} py-2")
                    for idx, line in enumerate(state["income"]):
                        _render_income_row(idx, line)
                    _render_yearly_total(state["income"])

            def _render_income_row(idx: int, line: IncomeLine) -> None:
                with ui.row().classes("w-full items-center gap-2"):
                    name_in = (
                        ui.input(label=t("budget_builder.line_name"), value=line.name)
                        .classes("flex-[2]")
                        .props("dense outlined")
                    )
                    amount_in = (
                        ui.number(
                            label=t("budget_builder.yearly_amount"),
                            value=float(line.amount),
                            min=0,
                            format="%.2f",
                        )
                        .classes("flex-1")
                        .props("dense outlined")
                    )

                    def _on_name(_e: Any, i: int = idx, ctrl: ui.input = name_in) -> None:
                        v = (ctrl.value or "").strip()
                        if v:
                            state["income"][i].name = v

                    def _on_amt(_e: Any, i: int = idx, ctrl: ui.number = amount_in) -> None:
                        state["income"][i].amount = Decimal(str(ctrl.value or 0))

                    name_in.on("blur", _on_name)
                    amount_in.on("blur", _on_amt)

                    ui.button(
                        icon="delete",
                        on_click=lambda i=idx: _remove_income(i),
                    ).props("flat dense round color=negative")

            def _add_income() -> None:
                state["income"].append(
                    IncomeLine(
                        name=t("budget_builder.default_income_name"),
                        amount=Decimal("0"),
                    )
                )
                _render_income()

            def _remove_income(i: int) -> None:
                state["income"].pop(i)
                _render_income()

            # ── Fixed section ────────────────────────────────────────────
            def _render_fixed() -> None:
                fixed_col.clear()
                with fixed_col:
                    if not state["fixed"]:
                        ui.label(t("budget_builder.fixed_empty")).classes(f"{BODY_MUTED} py-2")
                    for idx, line in enumerate(state["fixed"]):
                        _render_fixed_row(idx, line)
                    _render_yearly_total(state["fixed"])

            def _render_fixed_row(idx: int, line: FixedLine) -> None:
                with ui.row().classes("w-full items-center gap-2"):
                    name_in = (
                        ui.input(label=t("budget_builder.line_name"), value=line.name)
                        .classes("flex-[2]")
                        .props("dense outlined")
                    )
                    amount_in = (
                        ui.number(
                            label=t("budget_builder.yearly_amount"),
                            value=float(line.amount),
                            min=0,
                            format="%.2f",
                        )
                        .classes("flex-1")
                        .props("dense outlined")
                    )
                    cat_in = (
                        ui.select(
                            options=cat_opts,
                            label=t("common.category"),
                            value=line.category_id,
                            with_input=True,
                            clearable=True,
                        )
                        .classes("flex-1")
                        .props("dense outlined")
                    )

                    def _on_name(_e: Any, i: int = idx, ctrl: ui.input = name_in) -> None:
                        v = (ctrl.value or "").strip()
                        if v:
                            state["fixed"][i].name = v

                    def _on_amt(_e: Any, i: int = idx, ctrl: ui.number = amount_in) -> None:
                        state["fixed"][i].amount = Decimal(str(ctrl.value or 0))

                    def _on_cat(_e: Any, i: int = idx, ctrl: ui.select = cat_in) -> None:
                        state["fixed"][i].category_id = ctrl.value or None

                    name_in.on("blur", _on_name)
                    amount_in.on("blur", _on_amt)
                    cat_in.on("update:model-value", _on_cat)

                    ui.button(
                        icon="delete",
                        on_click=lambda i=idx: _remove_fixed(i),
                    ).props("flat dense round color=negative")

            def _add_fixed() -> None:
                state["fixed"].append(
                    FixedLine(
                        name=t("budget_builder.default_fixed_name"),
                        amount=Decimal("0"),
                        category_id=None,
                    )
                )
                _render_fixed()

            def _remove_fixed(i: int) -> None:
                state["fixed"].pop(i)
                _render_fixed()

            # ── Variable section ─────────────────────────────────────────
            def _render_variable() -> None:
                variable_col.clear()
                with variable_col:
                    if not state["variable"]:
                        ui.label(t("budget_builder.variable_empty")).classes(f"{BODY_MUTED} py-2")
                    for idx, line in enumerate(state["variable"]):
                        _render_variable_row(idx, line)
                    _render_yearly_total(state["variable"])

            def _render_variable_row(idx: int, line: VariableLine) -> None:
                with ui.row().classes("w-full items-center gap-2"):
                    name_in = (
                        ui.input(label=t("budget_builder.line_name"), value=line.name)
                        .classes("flex-[2]")
                        .props("dense outlined")
                    )
                    amount_in = (
                        ui.number(
                            label=t("budget_builder.yearly_amount"),
                            value=float(line.amount),
                            min=0,
                            format="%.2f",
                        )
                        .classes("flex-1")
                        .props("dense outlined")
                    )
                    cat_in = (
                        ui.select(
                            options=cat_opts,
                            label=t("common.category"),
                            value=line.category_id,
                            with_input=True,
                        )
                        .classes("flex-1")
                        .props("dense outlined")
                    )

                    def _on_name(_e: Any, i: int = idx, ctrl: ui.input = name_in) -> None:
                        v = (ctrl.value or "").strip()
                        if v:
                            state["variable"][i].name = v

                    def _on_amt(_e: Any, i: int = idx, ctrl: ui.number = amount_in) -> None:
                        state["variable"][i].amount = Decimal(str(ctrl.value or 0))

                    def _on_cat(_e: Any, i: int = idx, ctrl: ui.select = cat_in) -> None:
                        if ctrl.value is not None:
                            state["variable"][i].category_id = int(ctrl.value)

                    name_in.on("blur", _on_name)
                    amount_in.on("blur", _on_amt)
                    cat_in.on("update:model-value", _on_cat)

                    ui.button(
                        icon="delete",
                        on_click=lambda i=idx: _remove_variable(i),
                    ).props("flat dense round color=negative")

            def _add_variable() -> None:
                first_cat = next(iter(cat_opts), None)
                if first_cat is None:
                    ui.notify(t("budget_builder.need_categories"), type="warning")
                    return
                state["variable"].append(
                    VariableLine(
                        name=t("budget_builder.default_variable_name"),
                        amount=Decimal("0"),
                        category_id=first_cat,
                    )
                )
                _render_variable()

            def _remove_variable(i: int) -> None:
                state["variable"].pop(i)
                _render_variable()

            def _render_yearly_total(lines: list[Any]) -> None:
                total = sum((ln.amount for ln in lines), Decimal("0"))
                with ui.row().classes("w-full justify-end"):
                    ui.label(
                        t("budget_builder.section_total", amount=_fmt(total))
                    ).classes(f"{BODY_MUTED} text-sm font-semibold")

            # ── Section cards ────────────────────────────────────────────
            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(t("budget_builder.section_income")).classes(SECTION_HEADING)
                    ui.button(
                        t("budget_builder.add_line"),
                        icon="add",
                        on_click=_add_income,
                    ).props("color=primary unelevated size=sm")
                ui.label(t("budget_builder.section_income_hint")).classes(BODY_MUTED)
                income_col = ui.column().classes("w-full gap-2 mt-2")

            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(t("budget_builder.section_fixed")).classes(SECTION_HEADING)
                    ui.button(
                        t("budget_builder.add_line"),
                        icon="add",
                        on_click=_add_fixed,
                    ).props("color=primary unelevated size=sm")
                ui.label(t("budget_builder.section_fixed_hint")).classes(BODY_MUTED)
                fixed_col = ui.column().classes("w-full gap-2 mt-2")

            with ui.card().classes(SECTION_CARD):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(t("budget_builder.section_variable")).classes(SECTION_HEADING)
                    ui.button(
                        t("budget_builder.add_line"),
                        icon="add",
                        on_click=_add_variable,
                    ).props("color=primary unelevated size=sm")
                ui.label(t("budget_builder.section_variable_hint")).classes(BODY_MUTED)
                variable_col = ui.column().classes("w-full gap-2 mt-2")

            with (
                ui.card().classes(SECTION_CARD),
                ui.row().classes("w-full items-center justify-between gap-3"),
            ):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("savings", size="1.4rem").classes("text-primary")
                    with ui.column().classes("gap-0"):
                        ui.label(t("budget_builder.reserves_heading")).classes(
                            "font-semibold"
                        )
                        ui.label(t("budget_builder.reserves_link_body")).classes(
                            BODY_MUTED
                        )
                ui.button(
                    t("budget_builder.reserves_open"),
                    icon="arrow_forward",
                    on_click=lambda: ui.navigate.to("/wizard/safety-funds"),
                ).props("flat color=primary")

            # ── Apply flow with diff dialog ──────────────────────────────
            with ui.dialog() as diff_dialog, ui.card().classes("w-[560px] gap-2"):
                diff_title = ui.label("").classes("text-lg font-bold")
                diff_summary = ui.label("").classes(BODY_MUTED)
                diff_col = ui.column().classes("w-full max-h-80 overflow-auto mt-2")
                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=diff_dialog.close).props("flat")
                    diff_apply_btn = ui.button(
                        t("budget_builder.apply_confirm"), icon="check"
                    ).props("color=primary unelevated")

            async def _on_apply() -> None:
                payload_now = _current_payload()
                async with AsyncSessionFactory() as s:
                    diff = await YearlyPlanService(s).diff(payload_now)

                total_touched = len(diff.added) + len(diff.updated)
                if total_touched == 0 and diff.unchanged_count > 0:
                    ui.notify(t("budget_builder.nothing_to_change"), type="info")
                    return
                if total_touched == 0:
                    ui.notify(t("budget_builder.empty_plan"), type="warning")
                    return

                diff_title.set_text(t("budget_builder.diff_title"))
                diff_summary.set_text(
                    t(
                        "budget_builder.diff_summary",
                        added=len(diff.added),
                        updated=len(diff.updated),
                        unchanged=diff.unchanged_count,
                    )
                )
                diff_col.clear()
                with diff_col:
                    if diff.added:
                        ui.label(t("budget_builder.diff_added_header")).classes(
                            "text-xs font-semibold uppercase text-slate-500 mt-2"
                        )
                        for e in diff.added[:30]:
                            ui.label(
                                f"{e.category_name} · {e.month:02d}/{payload_now.year} "
                                f"→ +{_fmt(e.proposed)}"
                            ).classes("text-sm")
                    if diff.updated:
                        ui.label(t("budget_builder.diff_updated_header")).classes(
                            "text-xs font-semibold uppercase text-slate-500 mt-3"
                        )
                        for e in diff.updated[:30]:
                            ui.label(
                                f"{e.category_name} · {e.month:02d}/{payload_now.year} "
                                f"→ {_fmt(e.current or Decimal(0))} ⇒ {_fmt(e.proposed)}"
                            ).classes("text-sm")

                async def _confirm() -> None:
                    async with AsyncSessionFactory() as s2:
                        await YearlyPlanService(s2).apply(payload_now)
                    diff_dialog.close()
                    ui.notify(t("budget_builder.applied"), type="positive")

                diff_apply_btn.on_click(_confirm)
                diff_dialog.open()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button(
                    t("budget_builder.view_budgets"),
                    icon="bar_chart",
                    on_click=lambda: ui.navigate.to("/budgets"),
                ).props("flat color=primary")
                ui.button(
                    t("budget_builder.apply"),
                    icon="check_circle",
                    on_click=_on_apply,
                ).props("color=primary unelevated size=lg")

            _render_income()
            _render_fixed()
            _render_variable()
