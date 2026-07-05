# SPDX-License-Identifier: AGPL-3.0-or-later
"""Savings rate over time report."""

from __future__ import annotations

from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import ReportService, SavingsRatePoint
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt, fmt_pct
from kaleta.views.reports_canned.scaffold import export_button, kpi, loading_label, report_header
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE, TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/savings-rate")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        state: dict[str, Any] = {"months": 12, "data": None}

        with page_layout(t("reports_lib.savings_rate")):
            report_header(t("reports_lib.savings_rate"), t("reports_lib.savings_rate_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> list[SavingsRatePoint]:
                    return await ReportService(session).savings_rate(int(state["months"]))

                state["data"] = await with_session(_fetch)
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                ui.select(
                    {6: "6", 12: "12", 24: "24"},
                    label=t("reports_lib.months"),
                    value=state["months"],
                    on_change=lambda e: (
                        state.update(months=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")

            @ui.refreshable
            def output() -> None:
                points: list[SavingsRatePoint] | None = state["data"]
                if points is None:
                    loading_label()
                    return

                avg_rate = ReportService.average_savings_rate_pct(points)
                latest = points[-1] if points else None

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(
                        t("reports_lib.latest_rate"),
                        fmt_pct(latest.rate_pct) if latest else "—",
                        "percent",
                        "green-7" if latest and (latest.rate_pct or 0) >= 20 else "orange-7",
                    )
                    kpi(
                        t("reports_lib.avg_rate"),
                        fmt_pct(avg_rate if points else None),
                        "bar_chart",
                        "primary",
                    )

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.rate_over_time")).classes(SECTION_TITLE)
                    labels = [p.label for p in points]
                    rates = [float(p.rate_pct) if p.rate_pct is not None else None for p in points]
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis", "valueFormatter": "{value}%"},
                                "grid": {
                                    "left": "3%",
                                    "right": "4%",
                                    "bottom": "12%",
                                    "containLabel": True,
                                },
                                "xAxis": {
                                    "type": "category",
                                    "data": labels,
                                    "axisLabel": {"rotate": 30},
                                },
                                "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}%"}},
                                "series": [
                                    {
                                        "name": t("reports_lib.savings_rate"),
                                        "type": "line",
                                        "data": rates,
                                        "smooth": True,
                                        "lineStyle": {"color": "#4caf50", "width": 3},
                                        "itemStyle": {"color": "#4caf50"},
                                        "areaStyle": {"color": "#4caf50", "opacity": 0.15},
                                    },
                                ],
                                "markLine": {
                                    "silent": True,
                                    "lineStyle": {"color": "#fb8c00", "type": "dashed"},
                                    "data": [{"yAxis": 20, "name": "20%"}],
                                },
                            },
                            is_dark,
                        )
                    ).classes("w-full h-72")

                cols = [
                    {
                        "name": "month",
                        "label": t("common.month"),
                        "field": "month",
                        "align": "left",
                    },
                    {
                        "name": "income",
                        "label": t("common.income"),
                        "field": "income",
                        "align": "right",
                    },
                    {
                        "name": "expenses",
                        "label": t("common.expense"),
                        "field": "expenses",
                        "align": "right",
                    },
                    {
                        "name": "savings",
                        "label": t("reports_lib.savings"),
                        "field": "savings",
                        "align": "right",
                    },
                    {
                        "name": "rate",
                        "label": t("reports_lib.savings_rate"),
                        "field": "rate",
                        "align": "right",
                    },
                ]
                rows = [
                    {
                        "month": p.label,
                        "income": fmt(p.income),
                        "expenses": fmt(p.expenses),
                        "savings": fmt(p.savings),
                        "rate": fmt_pct(p.rate_pct),
                    }
                    for p in points
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    csv_download(
                        "savings_rate.csv",
                        [
                            t("common.month"),
                            t("common.income"),
                            t("common.expense"),
                            t("reports_lib.savings"),
                            t("reports_lib.savings_rate"),
                        ],
                        [
                            [p.label, p.income, p.expenses, p.savings, fmt_pct(p.rate_pct)]
                            for p in points
                        ],
                    )

                export_button(_export)

            output()
            await _load()
