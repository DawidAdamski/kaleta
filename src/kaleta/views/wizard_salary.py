# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard panel: pay yourself a salary out of irregular income."""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import app, ui

from kaleta.exceptions import KaletaError
from kaleta.i18n import t
from kaleta.schemas.salary import SalaryBasis, SalaryPlanCreate, SalaryProposal
from kaleta.services import AccountService, SalaryService, with_session
from kaleta.services.salary_service import MIN_HISTORY_MONTHS
from kaleta.views.chart_utils import (
    CHART_INCOME,
    CHART_NET_LINE,
    CHART_TEAL,
    apply_dark,
)
from kaleta.views.error_handling import notify_kaleta_error
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    KPI_VALUE,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

_WINDOW_CHOICES = [6, 12, 24]


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f}"


def _first_of_next_month() -> datetime.date:
    today = datetime.date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return datetime.date(year, month, 1)


def _basis_options() -> dict[str, str]:
    return {
        SalaryBasis.WORST.value: t("salary.basis_worst"),
        SalaryBasis.P25.value: t("salary.basis_p25"),
        SalaryBasis.MEDIAN.value: t("salary.basis_median"),
    }


def _buffer_chart(proposal: SalaryProposal, is_dark: bool) -> dict[str, Any]:
    """Monthly income bars against the salary line, with the buffer on top."""
    labels = [p.label for p in proposal.projection]
    options: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "legend": {
            "data": [t("salary.chart_income"), t("salary.chart_salary"), t("salary.chart_buffer")]
        },
        "grid": {"left": 60, "right": 20, "top": 40, "bottom": 40},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": [
            {
                "name": t("salary.chart_income"),
                "type": "bar",
                "data": [float(p.income) for p in proposal.projection],
                "itemStyle": {"color": CHART_INCOME},
            },
            {
                "name": t("salary.chart_salary"),
                "type": "line",
                "data": [float(proposal.salary)] * len(labels),
                "itemStyle": {"color": CHART_NET_LINE},
                "lineStyle": {"width": 2, "type": "dashed"},
                "symbol": "none",
            },
            {
                "name": t("salary.chart_buffer"),
                "type": "line",
                "data": [float(p.buffer) for p in proposal.projection],
                "itemStyle": {"color": CHART_TEAL},
                "lineStyle": {"width": 2},
                "symbol": "circle",
                "symbolSize": 6,
            },
        ],
    }
    return apply_dark(options, is_dark)


def register() -> None:
    @ui.page("/wizard/pay-yourself")
    async def pay_yourself_page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        state: dict[str, Any] = {
            "window_months": 12,
            "basis": SalaryBasis.WORST,
            "override": None,
        }

        async def _load(session: Any) -> tuple[SalaryProposal, dict[int, str]]:
            proposal = await SalaryService(session).propose(
                window_months=int(state["window_months"]),
                basis=state["basis"],
                override=state["override"],
            )
            accounts = await AccountService(session).list()
            return proposal, {a.id: a.name for a in accounts}

        proposal, account_opts = await with_session(_load)

        with page_layout(t("salary.title"), wide=True):
            with ui.column().classes("gap-1"):
                ui.label(t("salary.title")).classes(PAGE_TITLE)
                ui.label(t("salary.subtitle")).classes(BODY_MUTED)

            body = ui.column().classes("w-full gap-6")

            async def _refresh() -> None:
                nonlocal proposal
                proposal, _ = await with_session(_load)
                _render()

            def _kpi(label: str, value: str, colour: str = "") -> None:
                with ui.column().classes("gap-0.5 min-w-[9rem]"):
                    ui.label(label).classes(BODY_MUTED)
                    ui.label(value).classes(f"{KPI_VALUE} {colour}".strip())

            # ── Sections ─────────────────────────────────────────────────

            def _render_window_picker() -> None:
                with (
                    ui.card().classes(SECTION_CARD),
                    ui.row().classes("items-center gap-4 flex-wrap"),
                ):
                    ui.label(t("salary.window")).classes("text-sm font-medium")
                    window_in = (
                        ui.select(
                            options={
                                n: t("salary.window_months", months=n) for n in _WINDOW_CHOICES
                            },
                            value=int(state["window_months"]),
                        )
                        .props("dense outlined")
                        .classes("w-52")
                    )

                    async def _on_window(event: Any) -> None:
                        state["window_months"] = int(event.value)
                        state["override"] = None
                        await _refresh()

                    window_in.on_value_change(_on_window)
                    ui.label(t("salary.window_hint")).classes(BODY_MUTED)

            def _render_empty() -> None:
                with ui.card().classes(f"{SECTION_CARD} items-center text-center gap-2"):
                    ui.icon("insights", size="2.5rem").classes("text-slate-400")
                    ui.label(t("salary.not_enough_heading")).classes(SECTION_HEADING)
                    ui.label(
                        t(
                            "salary.not_enough_body",
                            months=len(proposal.months),
                            needed=MIN_HISTORY_MONTHS,
                        )
                    ).classes(BODY_MUTED)

            def _render_variability() -> None:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("salary.variability")).classes(SECTION_HEADING)
                    with ui.row().classes("gap-8 flex-wrap mt-2"):
                        _kpi(t("salary.worst_month"), _fmt(proposal.worst), AMOUNT_EXPENSE)
                        _kpi(t("salary.median_month"), _fmt(proposal.median))
                        _kpi(t("salary.best_month"), _fmt(proposal.best), AMOUNT_INCOME)
                        _kpi(t("salary.months_counted"), str(len(proposal.months)))
                    if proposal.is_multi_currency:
                        ui.label(
                            t(
                                "salary.multi_currency_warning",
                                currencies=", ".join(proposal.currencies),
                            )
                        ).classes(f"{BODY_MUTED} text-amber-700 mt-2")

            def _render_proposal() -> None:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("salary.proposal")).classes(SECTION_HEADING)
                    with ui.row().classes("items-end gap-4 flex-wrap mt-2"):
                        basis_in = (
                            ui.select(
                                options=_basis_options(),
                                value=proposal.basis.value,
                                label=t("salary.basis"),
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        amount_in = (
                            ui.number(
                                label=t("salary.monthly_salary"),
                                value=float(proposal.salary),
                                min=0,
                                step=100,
                                format="%.2f",
                            )
                            .props("dense outlined")
                            .classes("w-48")
                        )
                        apply_btn = ui.button(t("salary.apply_override")).props(
                            "outline color=primary size=md"
                        )

                    async def _on_basis(event: Any) -> None:
                        state["basis"] = SalaryBasis(event.value)
                        state["override"] = None
                        await _refresh()

                    async def _on_apply() -> None:
                        try:
                            state["override"] = Decimal(str(amount_in.value or 0))
                        except (InvalidOperation, ValueError):
                            ui.notify(t("salary.invalid_amount"), type="negative")
                            return
                        await _refresh()

                    basis_in.on_value_change(_on_basis)
                    apply_btn.on_click(_on_apply)

                    ui.label(
                        t(
                            "salary.buffer_summary",
                            salary=_fmt(proposal.salary),
                            buffer=_fmt(proposal.final_buffer),
                            months=len(proposal.projection),
                        )
                    ).classes(f"{BODY_MUTED} mt-3")

            def _render_chart() -> None:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("salary.buffer_projection")).classes(SECTION_HEADING)
                    ui.echart(_buffer_chart(proposal, is_dark)).classes("w-full h-80")

            def _render_action() -> None:
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("salary.create_heading")).classes(SECTION_HEADING)
                    if len(account_opts) < 2:
                        ui.label(t("salary.need_two_accounts")).classes(BODY_MUTED)
                        return
                    ids = list(account_opts)
                    with ui.row().classes("items-end gap-4 flex-wrap mt-2"):
                        name_in = (
                            ui.input(
                                label=t("salary.plan_name"), value=t("salary.default_plan_name")
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        from_in = (
                            ui.select(
                                options=account_opts,
                                value=ids[0],
                                label=t("salary.from_account"),
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        to_in = (
                            ui.select(
                                options=account_opts, value=ids[1], label=t("salary.to_account")
                            )
                            .props("dense outlined")
                            .classes("w-56")
                        )
                        start_in = (
                            ui.input(
                                label=t("salary.start_date"),
                                value=str(_first_of_next_month()),
                            )
                            .props("dense outlined type=date")
                            .classes("w-48")
                        )
                        create_btn = ui.button(t("salary.create_plan"), icon="event_repeat").props(
                            "color=primary unelevated size=md"
                        )

                    async def _on_create() -> None:
                        try:
                            payload = SalaryPlanCreate(
                                name=str(name_in.value or "").strip(),
                                amount=proposal.salary,
                                from_account_id=int(from_in.value),
                                to_account_id=int(to_in.value),
                                start_date=datetime.date.fromisoformat(str(start_in.value)),
                            )
                        except (ValueError, InvalidOperation):
                            ui.notify(t("salary.invalid_plan"), type="negative")
                            return

                        async def _create(session: Any) -> None:
                            await SalaryService(session).create_salary_plan(payload)

                        try:
                            await with_session(_create)
                        except KaletaError as exc:
                            notify_kaleta_error(exc)
                            return
                        ui.notify(t("salary.plan_created"), type="positive")

                    create_btn.on_click(_on_create)

            def _render() -> None:
                body.clear()
                with body:
                    _render_window_picker()
                    if not proposal.has_enough_history:
                        _render_empty()
                        return
                    _render_variability()
                    _render_proposal()
                    _render_chart()
                    _render_action()

            _render()
