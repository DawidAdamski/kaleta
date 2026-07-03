"""Budget variance report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import BudgetVarianceReport, ReportService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt, fmt_pct
from kaleta.views.reports_canned.scaffold import (
    export_button,
    kpi,
    loading_label,
    month_controls,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE, TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/budget-variance")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.budget_variance")):
            report_header(t("reports_lib.budget_variance"), t("reports_lib.budget_variance_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> BudgetVarianceReport:
                    return await ReportService(session).budget_variance(
                        state["year"], state["month"]
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                rep: BudgetVarianceReport | None = state["data"]
                if rep is None:
                    loading_label()
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(
                        t("reports_lib.total_planned"),
                        fmt(rep.total_planned),
                        "event_note",
                        "primary",
                    )
                    kpi(
                        t("reports_lib.total_actual"),
                        fmt(rep.total_actual),
                        "fact_check",
                        "orange-7",
                    )
                    kpi(
                        t("reports_lib.over_budget_count"),
                        str(len(rep.over_budget_rows)),
                        "warning",
                        "red-7" if rep.over_budget_rows else "grey-7",
                    )

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.plan_vs_actual")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "legend": {
                                    "data": [t("reports_lib.planned"), t("reports_lib.actual")],
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
                                    "data": [r.category for r in rep.rows],
                                    "axisLabel": {"rotate": 30},
                                },
                                "yAxis": {"type": "value"},
                                "series": [
                                    {
                                        "name": t("reports_lib.planned"),
                                        "type": "bar",
                                        "data": [float(r.planned) for r in rep.rows],
                                        "itemStyle": {"color": "#1976d2"},
                                    },
                                    {
                                        "name": t("reports_lib.actual"),
                                        "type": "bar",
                                        "data": [float(r.actual) for r in rep.rows],
                                        "itemStyle": {"color": "#fb8c00"},
                                    },
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                cols = [
                    {
                        "name": "category",
                        "label": t("common.category"),
                        "field": "category",
                        "align": "left",
                    },
                    {
                        "name": "planned",
                        "label": t("reports_lib.planned"),
                        "field": "planned",
                        "align": "right",
                    },
                    {
                        "name": "actual",
                        "label": t("reports_lib.actual"),
                        "field": "actual",
                        "align": "right",
                    },
                    {
                        "name": "variance",
                        "label": t("reports_lib.variance"),
                        "field": "variance",
                        "align": "right",
                    },
                    {
                        "name": "variance_pct",
                        "label": "%",
                        "field": "variance_pct",
                        "align": "right",
                    },
                ]
                rows = [
                    {
                        "category": r.category,
                        "planned": fmt(r.planned),
                        "actual": fmt(r.actual),
                        "variance": fmt(r.variance),
                        "variance_pct": fmt_pct(r.variance_pct),
                        "over": r.over_budget,
                    }
                    for r in rep.rows
                ]
                tbl = ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")
                tbl.add_slot(
                    "body-cell-variance",
                    '<q-td :props="props" class="text-right">'
                    "<span :class=\"props.row.over ? 'text-negative font-semibold' : "
                    "'text-positive'\">{{ props.row.variance }}</span></q-td>",
                )

                def _export() -> None:
                    csv_download(
                        f"budget_variance_{rep.year}_{rep.month:02d}.csv",
                        [
                            t("common.category"),
                            t("reports_lib.planned"),
                            t("reports_lib.actual"),
                            t("reports_lib.variance"),
                            "variance_pct",
                        ],
                        [
                            [r.category, r.planned, r.actual, r.variance, fmt_pct(r.variance_pct)]
                            for r in rep.rows
                        ],
                    )

                export_button(_export)

            output()
            await _load()
