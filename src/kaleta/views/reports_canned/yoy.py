# SPDX-License-Identifier: AGPL-3.0-or-later
"""Year-over-year comparison report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.schemas.transaction import TransactionType
from kaleta.services import with_session
from kaleta.services.report_service import ReportService, YoYComparison
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt, fmt_pct
from kaleta.views.reports_canned.scaffold import export_button, kpi, loading_label, report_header
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE


def register() -> None:
    @ui.page("/reports/yoy")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {
            "year": today.year,
            "basis": TransactionType.EXPENSE.value,
            "data": None,
        }

        with page_layout(t("reports_lib.yoy")):
            report_header(t("reports_lib.yoy"), t("reports_lib.yoy_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> YoYComparison:
                    return await ReportService(session).yoy_comparison(
                        state["year"], TransactionType(state["basis"])
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                years = list(range(today.year - 5, today.year + 1))
                ui.select(
                    {y: str(y) for y in years},
                    label=t("common.year"),
                    value=state["year"],
                    on_change=lambda e: (
                        state.update(year=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")
                ui.select(
                    {"expense": t("common.expense"), "income": t("common.income")},
                    label=t("reports_lib.basis"),
                    value=state["basis"],
                    on_change=lambda e: (
                        state.update(basis=e.value),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-44")

            @ui.refreshable
            def output() -> None:
                rep: YoYComparison | None = state["data"]
                if rep is None:
                    loading_label()
                    return

                delta = rep.total_delta

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(str(rep.year), fmt(rep.total_this_year), "today", "primary")
                    kpi(str(rep.year - 1), fmt(rep.total_last_year), "history", "grey-7")
                    kpi(
                        t("reports_lib.delta"),
                        fmt(delta),
                        "trending_flat",
                        "red-7" if delta > 0 and rep.basis == "expense" else "green-7",
                    )

                months = [datetime.date(2000, m, 1).strftime("%b") for m in range(1, 13)]
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.yoy")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "legend": {"data": [str(rep.year), str(rep.year - 1)], "bottom": 0},
                                "grid": {
                                    "left": "3%",
                                    "right": "4%",
                                    "bottom": "12%",
                                    "containLabel": True,
                                },
                                "xAxis": {"type": "category", "data": months},
                                "yAxis": {"type": "value"},
                                "series": [
                                    {
                                        "name": str(rep.year),
                                        "type": "bar",
                                        "data": [float(r.this_year) for r in rep.rows],
                                        "itemStyle": {"color": "#1976d2"},
                                    },
                                    {
                                        "name": str(rep.year - 1),
                                        "type": "bar",
                                        "data": [float(r.last_year) for r in rep.rows],
                                        "itemStyle": {"color": "#bdbdbd"},
                                    },
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                def _export() -> None:
                    csv_download(
                        f"yoy_{rep.year}.csv",
                        [
                            t("common.month"),
                            str(rep.year),
                            str(rep.year - 1),
                            t("reports_lib.delta"),
                            "delta_pct",
                        ],
                        [
                            [
                                months[r.month - 1],
                                r.this_year,
                                r.last_year,
                                r.delta,
                                fmt_pct(r.delta_pct),
                            ]
                            for r in rep.rows
                        ],
                    )

                export_button(_export)

            output()
            await _load()
