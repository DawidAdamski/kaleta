# SPDX-License-Identifier: AGPL-3.0-or-later
"""Spending by category report."""

from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import ReportService, SpendingByCategory
from kaleta.views.chart_utils import apply_dark
from kaleta.views.components.empty_state import report_no_data_label
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt
from kaleta.views.reports_canned.scaffold import (
    date_range_controls,
    export_button,
    loading_label,
    report_header,
)
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE, TABLE_SURFACE


def register() -> None:
    @ui.page("/reports/spending-by-category")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {
            "start": today.replace(day=1).isoformat(),
            "end": today.isoformat(),
            "data": None,
        }

        with page_layout(t("reports_lib.spending_by_category")):
            report_header(
                t("reports_lib.spending_by_category"),
                t("reports_lib.spending_by_category_desc"),
            )

            async def _load() -> None:
                async def _fetch(session: Any) -> SpendingByCategory:
                    return await ReportService(session).spending_by_category(
                        datetime.date.fromisoformat(state["start"]),
                        datetime.date.fromisoformat(state["end"]) + datetime.timedelta(days=1),
                    )

                state["data"] = await with_session(_fetch)
                output.refresh()

            date_range_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                rep: SpendingByCategory | None = state["data"]
                if rep is None:
                    loading_label()
                    return
                if not rep.rows:
                    report_no_data_label()
                    return

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.spend_distribution")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                                "legend": {"orient": "vertical", "left": "right", "top": "middle"},
                                "series": [
                                    {
                                        "name": t("reports_lib.spending_by_category"),
                                        "type": "pie",
                                        "radius": ["40%", "70%"],
                                        "avoidLabelOverlap": True,
                                        "itemStyle": {"borderRadius": 6, "borderWidth": 2},
                                        "label": {"show": False},
                                        "data": [
                                            {"name": r.category, "value": float(r.amount)}
                                            for r in rep.rows
                                        ],
                                    }
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-96")

                cols = [
                    {
                        "name": "category",
                        "label": t("common.category"),
                        "field": "category",
                        "align": "left",
                    },
                    {
                        "name": "amount",
                        "label": t("common.amount"),
                        "field": "amount",
                        "align": "right",
                    },
                    {"name": "share", "label": "%", "field": "share", "align": "right"},
                ]
                rows = [
                    {
                        "category": r.category,
                        "amount": fmt(r.amount),
                        "share": f"{rep.share_pct(r.amount):.1f}%",
                    }
                    for r in rep.rows
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    csv_download(
                        f"spending_by_category_{rep.start}_{rep.end}.csv",
                        [t("common.category"), t("common.amount"), "share_pct"],
                        [
                            [r.category, r.amount, f"{rep.share_pct(r.amount):.1f}"]
                            for r in rep.rows
                        ],
                    )

                export_button(_export)

            output()
            await _load()
