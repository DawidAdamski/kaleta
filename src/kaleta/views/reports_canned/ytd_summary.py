"""Year-to-date summary report."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.report_service import ReportService, YTDSummary
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.reports_canned.formatters import csv_download, fmt, fmt_pct
from kaleta.views.reports_canned.scaffold import export_button, kpi, loading_label, report_header
from kaleta.views.theme import SECTION_CARD, SECTION_TITLE


def register() -> None:
    @ui.page("/reports/ytd-summary")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "data": None}

        with page_layout(t("reports_lib.ytd_summary")):
            report_header(t("reports_lib.ytd_summary"), t("reports_lib.ytd_summary_desc"))

            async def _load() -> None:
                async def _fetch(session: Any) -> YTDSummary:
                    return await ReportService(session).ytd_summary(state["year"])

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

            @ui.refreshable
            def output() -> None:
                rep: YTDSummary | None = state["data"]
                if rep is None:
                    loading_label()
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    kpi(t("reports_lib.ytd_income"), fmt(rep.income), "trending_up", "green-7")
                    kpi(t("reports_lib.ytd_expenses"), fmt(rep.expenses), "trending_down", "red-7")
                    kpi(
                        t("reports_lib.ytd_net"),
                        fmt(rep.net),
                        "account_balance",
                        "green-7" if rep.net >= 0 else "red-7",
                    )
                    kpi(
                        t("reports_lib.savings_rate"),
                        fmt_pct(rep.savings_rate_pct),
                        "savings",
                        "primary",
                    )

                if rep.top_expense_categories:
                    with ui.card().classes(SECTION_CARD):
                        ui.label(t("reports_lib.top_expense_cats")).classes(SECTION_TITLE)
                        ui.echart(
                            apply_dark(
                                {
                                    "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                                    "series": [
                                        {
                                            "type": "pie",
                                            "radius": ["30%", "65%"],
                                            "data": [
                                                {"name": c.category, "value": float(c.amount)}
                                                for c in rep.top_expense_categories
                                            ],
                                        }
                                    ],
                                },
                                is_dark,
                            )
                        ).classes("w-full h-80")

                def _export() -> None:
                    summary_rows = [
                        ["income", "", rep.income],
                        ["expenses", "", rep.expenses],
                        ["net", "", rep.net],
                        ["savings_rate_pct", "", rep.savings_rate_pct or Decimal("0")],
                    ]
                    cat_rows = [
                        ["category", c.category, c.amount] for c in rep.top_expense_categories
                    ]
                    csv_download(
                        f"ytd_summary_{rep.year}.csv",
                        ["kind", "label", t("common.amount")],
                        summary_rows + cat_rows,
                    )

                export_button(_export)

            output()
            await _load()
