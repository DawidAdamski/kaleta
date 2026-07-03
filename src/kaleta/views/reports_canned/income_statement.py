"""Income statement report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import IncomeStatement, ReportService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import (
    export_button,
    kpi,
    loading_label,
    month_controls,
    render_category_table,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE


def register() -> None:
    @ui.page("/reports/income-statement")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.income_statement")):
            report_header(
                t("reports_lib.income_statement"),
                t("reports_lib.income_statement_desc"),
            )

            async def _load() -> None:
                async def _fetch(session: Any) -> IncomeStatement:
                    return await ReportService(session).income_statement(
                        state["year"], state["month"]
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                stmt: IncomeStatement | None = state["data"]
                if stmt is None:
                    loading_label()
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(
                        t("reports_lib.total_income"),
                        fmt(stmt.total_income),
                        "trending_up",
                        "green-7",
                    )
                    kpi(
                        t("reports_lib.total_expenses"),
                        fmt(stmt.total_expenses),
                        "trending_down",
                        "red-7",
                    )
                    kpi(
                        t("reports_lib.net_income"),
                        fmt(stmt.net_income),
                        "account_balance_wallet",
                        "green-7" if stmt.net_income >= 0 else "red-7",
                    )

                labels = [r.category for r in stmt.income_by_category] + [
                    r.category for r in stmt.expense_by_category
                ]
                income_vals = [float(r.amount) for r in stmt.income_by_category] + [0] * len(
                    stmt.expense_by_category
                )
                expense_vals = [0] * len(stmt.income_by_category) + [
                    float(r.amount) for r in stmt.expense_by_category
                ]
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.category_breakdown")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "legend": {
                                    "data": [t("common.income"), t("common.expense")],
                                    "bottom": 0,
                                },
                                "grid": {
                                    "left": "3%",
                                    "right": "4%",
                                    "bottom": "15%",
                                    "containLabel": True,
                                },
                                "xAxis": {
                                    "type": "category",
                                    "data": labels,
                                    "axisLabel": {"rotate": 30},
                                },
                                "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}"}},
                                "series": [
                                    {
                                        "name": t("common.income"),
                                        "type": "bar",
                                        "data": income_vals,
                                        "itemStyle": {"color": "#4caf50"},
                                    },
                                    {
                                        "name": t("common.expense"),
                                        "type": "bar",
                                        "data": expense_vals,
                                        "itemStyle": {"color": "#ef5350"},
                                    },
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                with ui.row().classes("w-full gap-3 flex-wrap"):
                    render_category_table(t("common.income"), stmt.income_by_category, "green-7")
                    render_category_table(t("common.expense"), stmt.expense_by_category, "red-7")

                def _export() -> None:
                    rows: list[list[Any]] = []
                    for r in stmt.income_by_category:
                        rows.append(["income", r.category, r.amount])
                    for r in stmt.expense_by_category:
                        rows.append(["expense", r.category, r.amount])
                    csv_download(
                        f"income_statement_{stmt.year}_{stmt.month:02d}.csv",
                        [t("common.type"), t("common.category"), t("common.amount")],
                        rows,
                    )

                export_button(_export)

            output()
            await _load()
