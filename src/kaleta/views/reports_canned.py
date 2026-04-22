"""Canned financial reports — landing page + per-report sub-routes.

Each report gets its own `@ui.page("/reports/<slug>")` so the URL is
bookmarkable / shareable, and a uniform layout: title + description + filter
controls + chart + table + CSV export.

The advanced drag-and-drop builder lives at `/reports/builder` (see
`views/reports.py`) and is linked from the landing page.
"""

from __future__ import annotations

import csv
import datetime
import io
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.models.transaction import TransactionType
from kaleta.services.report_service import (
    BudgetVarianceReport,
    CashFlowStatement,
    IncomeStatement,
    LargeTransaction,
    MerchantSpend,
    ReportService,
    SavingsRatePoint,
    SpendingByCategory,
    YoYComparison,
    YTDSummary,
)
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout
from kaleta.views.theme import PAGE_TITLE, SECTION_CARD, SECTION_TITLE, TABLE_SURFACE

# ── Report catalog ────────────────────────────────────────────────────────────

_REPORTS: list[tuple[str, str, str, str, str]] = [
    # (slug, title_key, desc_key, icon, colour)
    ("income-statement", "reports_lib.income_statement", "reports_lib.income_statement_desc",
     "receipt_long", "primary"),
    ("cash-flow", "reports_lib.cash_flow", "reports_lib.cash_flow_desc",
     "waves", "blue-7"),
    ("budget-variance", "reports_lib.budget_variance", "reports_lib.budget_variance_desc",
     "rule", "orange-7"),
    ("savings-rate", "reports_lib.savings_rate", "reports_lib.savings_rate_desc",
     "savings", "green-7"),
    ("spending-by-category", "reports_lib.spending_by_category",
     "reports_lib.spending_by_category_desc", "donut_large", "purple-7"),
    ("top-merchants", "reports_lib.top_merchants", "reports_lib.top_merchants_desc",
     "storefront", "teal-7"),
    ("yoy", "reports_lib.yoy", "reports_lib.yoy_desc",
     "compare_arrows", "indigo-7"),
    ("ytd-summary", "reports_lib.ytd_summary", "reports_lib.ytd_summary_desc",
     "today", "cyan-7"),
    ("largest-transactions", "reports_lib.largest_transactions",
     "reports_lib.largest_transactions_desc", "format_list_numbered", "pink-7"),
    ("net-worth-statement", "reports_lib.net_worth_statement",
     "reports_lib.net_worth_statement_desc", "account_balance", "deep-purple-7"),
]


# ── CSV helper ────────────────────────────────────────────────────────────────


def _csv_download(filename: str, headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> None:
    """Build a CSV in memory and trigger a browser download."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(
            "" if v is None else (f"{v:.2f}" if isinstance(v, Decimal) else v) for v in row
        )
    ui.download(buf.getvalue().encode("utf-8-sig"), filename=filename)


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f} zł"


def _fmt_pct(pct: Decimal | None) -> str:
    return f"{pct:.1f}%" if pct is not None else "—"


# ── Shared page scaffold ──────────────────────────────────────────────────────


def _report_header(title: str, description: str) -> None:
    ui.label(title).classes(PAGE_TITLE)
    ui.label(description).classes("text-sm text-grey-6 -mt-2 mb-2")


def _month_controls(
    state: dict[str, Any],
    on_change: Any,
) -> None:
    """Year+month selectors. Mutates `state["year"]` / `state["month"]`."""
    today = datetime.date.today()
    years = [y for y in range(today.year - 5, today.year + 1)]
    months = {i: datetime.date(2000, i, 1).strftime("%B") for i in range(1, 13)}
    with ui.row().classes("items-end gap-3 mb-2"):
        ui.select(
            {y: str(y) for y in years},
            label=t("common.year"),
            value=state["year"],
            on_change=lambda e: (state.update(year=int(e.value)), on_change()),
        ).classes("w-32")
        ui.select(
            months,
            label=t("common.month"),
            value=state["month"],
            on_change=lambda e: (state.update(month=int(e.value)), on_change()),
        ).classes("w-40")


# ── Landing page ──────────────────────────────────────────────────────────────


def _register_landing() -> None:
    @ui.page("/reports")
    async def reports_landing() -> None:
        with page_layout(t("reports_lib.title")):
            ui.label(t("reports_lib.title")).classes(PAGE_TITLE)
            ui.label(t("reports_lib.intro")).classes("text-sm text-grey-6 -mt-2 mb-4")

            with ui.row().classes("w-full gap-4 flex-wrap"):
                for slug, title_key, desc_key, icon, colour in _REPORTS:
                    with ui.card().classes(
                        "p-4 flex-1 min-w-64 max-w-80 cursor-pointer hover:shadow-lg"
                    ) as card:
                        with ui.row().classes("items-start gap-3 w-full no-wrap"):
                            ui.icon(icon, color=colour).classes("text-3xl")
                            with ui.column().classes("gap-1 flex-1 min-w-0"):
                                ui.label(t(title_key)).classes("text-base font-semibold")
                                ui.label(t(desc_key)).classes("text-xs text-grey-6 leading-snug")
                        card.on(
                            "click",
                            lambda s=slug: ui.navigate.to(f"/reports/{s}"),
                        )

            ui.separator().classes("my-4")
            with ui.row().classes("items-center gap-2"):
                ui.icon("build", color="grey-6")
                ui.label(t("reports_lib.advanced_builder_hint")).classes("text-sm text-grey-6")
                ui.button(
                    t("reports_lib.open_builder"),
                    icon="open_in_new",
                    on_click=lambda: ui.navigate.to("/reports/builder"),
                ).props("flat color=primary")


# ── Report 1: Income Statement ────────────────────────────────────────────────


def _register_income_statement() -> None:
    @ui.page("/reports/income-statement")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.income_statement")):
            _report_header(
                t("reports_lib.income_statement"),
                t("reports_lib.income_statement_desc"),
            )

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).income_statement(
                        state["year"], state["month"]
                    )
                output.refresh()

            _month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                stmt: IncomeStatement | None = state["data"]
                if stmt is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                # KPI trio
                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(t("reports_lib.total_income"), _fmt(stmt.total_income), "trending_up",
                         "green-7")
                    _kpi(t("reports_lib.total_expenses"), _fmt(stmt.total_expenses),
                         "trending_down", "red-7")
                    _kpi(
                        t("reports_lib.net_income"),
                        _fmt(stmt.net_income),
                        "account_balance_wallet",
                        "green-7" if stmt.net_income >= 0 else "red-7",
                    )

                # Bar chart — income green, expense red
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
                                "legend": {"data": [t("common.income"), t("common.expense")],
                                           "bottom": 0},
                                "grid": {"left": "3%", "right": "4%", "bottom": "15%",
                                         "containLabel": True},
                                "xAxis": {"type": "category", "data": labels,
                                          "axisLabel": {"rotate": 30}},
                                "yAxis": {"type": "value", "axisLabel": {"formatter": "{value}"}},
                                "series": [
                                    {"name": t("common.income"), "type": "bar", "data": income_vals,
                                     "itemStyle": {"color": "#4caf50"}},
                                    {"name": t("common.expense"), "type": "bar",
                                     "data": expense_vals, "itemStyle": {"color": "#ef5350"}},
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                # Tables
                with ui.row().classes("w-full gap-3 flex-wrap"):
                    _render_category_table(
                        t("common.income"), stmt.income_by_category, "green-7"
                    )
                    _render_category_table(
                        t("common.expense"), stmt.expense_by_category, "red-7"
                    )

                def _export() -> None:
                    rows: list[list[Any]] = []
                    for r in stmt.income_by_category:
                        rows.append(["income", r.category, r.amount])
                    for r in stmt.expense_by_category:
                        rows.append(["expense", r.category, r.amount])
                    _csv_download(
                        f"income_statement_{stmt.year}_{stmt.month:02d}.csv",
                        [t("common.type"), t("common.category"), t("common.amount")],
                        rows,
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 2: Cash Flow Statement ─────────────────────────────────────────────


def _register_cash_flow() -> None:
    @ui.page("/reports/cash-flow")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.cash_flow")):
            _report_header(t("reports_lib.cash_flow"), t("reports_lib.cash_flow_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).cash_flow_statement(
                        state["year"], state["month"]
                    )
                output.refresh()

            _month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                cfs: CashFlowStatement | None = state["data"]
                if cfs is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(t("reports_lib.inflows"), _fmt(cfs.total_inflows), "south_west", "green-7")
                    _kpi(t("reports_lib.outflows"), _fmt(cfs.total_outflows), "north_east",
                         "red-7")
                    _kpi(
                        t("reports_lib.net_cash_flow"),
                        _fmt(cfs.net_cash_flow),
                        "sync_alt",
                        "green-7" if cfs.net_cash_flow >= 0 else "red-7",
                    )

                # Waterfall-ish: stacked bar of inflows vs outflows
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.flows_by_category")).classes(SECTION_TITLE)
                    in_labels = [r.category for r in cfs.inflows]
                    in_vals = [float(r.amount) for r in cfs.inflows]
                    out_labels = [r.category for r in cfs.outflows]
                    out_vals = [-float(r.amount) for r in cfs.outflows]
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "grid": {"left": "3%", "right": "4%", "bottom": "12%",
                                         "containLabel": True},
                                "xAxis": {"type": "value"},
                                "yAxis": {"type": "category", "data": in_labels + out_labels},
                                "series": [
                                    {"name": t("reports_lib.inflows"), "type": "bar",
                                     "data": in_vals + [0] * len(out_labels),
                                     "itemStyle": {"color": "#4caf50"}},
                                    {"name": t("reports_lib.outflows"), "type": "bar",
                                     "data": [0] * len(in_labels) + out_vals,
                                     "itemStyle": {"color": "#ef5350"}},
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full").style("height: 400px")

                def _export() -> None:
                    rows: list[list[Any]] = []
                    for r in cfs.inflows:
                        rows.append(["inflow", r.category, r.amount])
                    for r in cfs.outflows:
                        rows.append(["outflow", r.category, r.amount])
                    _csv_download(
                        f"cash_flow_{cfs.year}_{cfs.month:02d}.csv",
                        [t("common.type"), t("common.category"), t("common.amount")],
                        rows,
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 3: Budget Variance ─────────────────────────────────────────────────


def _register_budget_variance() -> None:
    @ui.page("/reports/budget-variance")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "month": today.month, "data": None}

        with page_layout(t("reports_lib.budget_variance")):
            _report_header(t("reports_lib.budget_variance"), t("reports_lib.budget_variance_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).budget_variance(
                        state["year"], state["month"]
                    )
                output.refresh()

            _month_controls(state, lambda: ui.timer(0.01, _load, once=True))

            @ui.refreshable
            def output() -> None:
                rep: BudgetVarianceReport | None = state["data"]
                if rep is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(t("reports_lib.total_planned"), _fmt(rep.total_planned),
                         "event_note", "primary")
                    _kpi(t("reports_lib.total_actual"), _fmt(rep.total_actual),
                         "fact_check", "orange-7")
                    _kpi(
                        t("reports_lib.over_budget_count"),
                        str(len(rep.over_budget_rows)),
                        "warning",
                        "red-7" if rep.over_budget_rows else "grey-7",
                    )

                # Bar chart: planned vs actual per category
                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.plan_vs_actual")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "legend": {"data": [
                                    t("reports_lib.planned"), t("reports_lib.actual")
                                ], "bottom": 0},
                                "grid": {"left": "3%", "right": "4%", "bottom": "15%",
                                         "containLabel": True},
                                "xAxis": {"type": "category",
                                          "data": [r.category for r in rep.rows],
                                          "axisLabel": {"rotate": 30}},
                                "yAxis": {"type": "value"},
                                "series": [
                                    {"name": t("reports_lib.planned"), "type": "bar",
                                     "data": [float(r.planned) for r in rep.rows],
                                     "itemStyle": {"color": "#1976d2"}},
                                    {"name": t("reports_lib.actual"), "type": "bar",
                                     "data": [float(r.actual) for r in rep.rows],
                                     "itemStyle": {"color": "#fb8c00"}},
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                cols = [
                    {"name": "category", "label": t("common.category"), "field": "category",
                     "align": "left"},
                    {"name": "planned", "label": t("reports_lib.planned"), "field": "planned",
                     "align": "right"},
                    {"name": "actual", "label": t("reports_lib.actual"), "field": "actual",
                     "align": "right"},
                    {"name": "variance", "label": t("reports_lib.variance"), "field": "variance",
                     "align": "right"},
                    {"name": "variance_pct", "label": "%", "field": "variance_pct",
                     "align": "right"},
                ]
                rows = [
                    {
                        "category": r.category,
                        "planned": _fmt(r.planned),
                        "actual": _fmt(r.actual),
                        "variance": _fmt(r.variance),
                        "variance_pct": _fmt_pct(r.variance_pct),
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
                    _csv_download(
                        f"budget_variance_{rep.year}_{rep.month:02d}.csv",
                        [t("common.category"), t("reports_lib.planned"), t("reports_lib.actual"),
                         t("reports_lib.variance"), "variance_pct"],
                        [
                            [r.category, r.planned, r.actual, r.variance,
                             _fmt_pct(r.variance_pct)]
                            for r in rep.rows
                        ],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 4: Savings Rate ────────────────────────────────────────────────────


def _register_savings_rate() -> None:
    @ui.page("/reports/savings-rate")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        state: dict[str, Any] = {"months": 12, "data": None}

        with page_layout(t("reports_lib.savings_rate")):
            _report_header(t("reports_lib.savings_rate"), t("reports_lib.savings_rate_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).savings_rate(int(state["months"]))
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
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                avg_rate: Decimal = (
                    sum(
                        (p.rate_pct or Decimal("0") for p in points),
                        start=Decimal("0"),
                    )
                    / len(points)
                    if points
                    else Decimal("0")
                )
                latest = points[-1] if points else None

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(
                        t("reports_lib.latest_rate"),
                        _fmt_pct(latest.rate_pct) if latest else "—",
                        "percent",
                        "green-7" if latest and (latest.rate_pct or 0) >= 20 else "orange-7",
                    )
                    _kpi(
                        t("reports_lib.avg_rate"),
                        _fmt_pct(avg_rate if points else None),
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
                                "grid": {"left": "3%", "right": "4%", "bottom": "12%",
                                         "containLabel": True},
                                "xAxis": {"type": "category", "data": labels,
                                          "axisLabel": {"rotate": 30}},
                                "yAxis": {"type": "value",
                                          "axisLabel": {"formatter": "{value}%"}},
                                "series": [
                                    {"name": t("reports_lib.savings_rate"), "type": "line",
                                     "data": rates, "smooth": True,
                                     "lineStyle": {"color": "#4caf50", "width": 3},
                                     "itemStyle": {"color": "#4caf50"},
                                     "areaStyle": {"color": "#4caf50", "opacity": 0.15}},
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
                    {"name": "month", "label": t("common.month"), "field": "month",
                     "align": "left"},
                    {"name": "income", "label": t("common.income"), "field": "income",
                     "align": "right"},
                    {"name": "expenses", "label": t("common.expense"), "field": "expenses",
                     "align": "right"},
                    {"name": "savings", "label": t("reports_lib.savings"), "field": "savings",
                     "align": "right"},
                    {"name": "rate", "label": t("reports_lib.savings_rate"), "field": "rate",
                     "align": "right"},
                ]
                rows = [
                    {
                        "month": p.label,
                        "income": _fmt(p.income),
                        "expenses": _fmt(p.expenses),
                        "savings": _fmt(p.savings),
                        "rate": _fmt_pct(p.rate_pct),
                    }
                    for p in points
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    _csv_download(
                        "savings_rate.csv",
                        [t("common.month"), t("common.income"), t("common.expense"),
                         t("reports_lib.savings"), t("reports_lib.savings_rate")],
                        [[p.label, p.income, p.expenses, p.savings, _fmt_pct(p.rate_pct)]
                         for p in points],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 5: Spending By Category ────────────────────────────────────────────


def _register_spending_by_category() -> None:
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
            _report_header(
                t("reports_lib.spending_by_category"),
                t("reports_lib.spending_by_category_desc"),
            )

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).spending_by_category(
                        datetime.date.fromisoformat(state["start"]),
                        datetime.date.fromisoformat(state["end"]) + datetime.timedelta(days=1),
                    )
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                ui.input(
                    t("transactions.date_from"), value=state["start"],
                    on_change=lambda e: (
                        state.update(start=e.value),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).props("type=date").classes("w-44")
                ui.input(
                    t("transactions.date_to"), value=state["end"],
                    on_change=lambda e: (
                        state.update(end=e.value),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).props("type=date").classes("w-44")

            @ui.refreshable
            def output() -> None:
                rep: SpendingByCategory | None = state["data"]
                if rep is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return
                if not rep.rows:
                    ui.label(t("reports.no_data")).classes("text-grey-5 py-8")
                    return

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.spend_distribution")).classes(SECTION_TITLE)
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "item",
                                            "formatter": "{b}: {c} ({d}%)"},
                                "legend": {"orient": "vertical", "left": "right", "top": "middle"},
                                "series": [{
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
                                }],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-96")

                cols = [
                    {"name": "category", "label": t("common.category"), "field": "category",
                     "align": "left"},
                    {"name": "amount", "label": t("common.amount"), "field": "amount",
                     "align": "right"},
                    {"name": "share", "label": "%", "field": "share", "align": "right"},
                ]
                total = rep.total or Decimal("1")
                rows = [
                    {
                        "category": r.category,
                        "amount": _fmt(r.amount),
                        "share": f"{(r.amount / total * 100):.1f}%",
                    }
                    for r in rep.rows
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    _csv_download(
                        f"spending_by_category_{rep.start}_{rep.end}.csv",
                        [t("common.category"), t("common.amount"), "share_pct"],
                        [
                            [r.category, r.amount, f"{(r.amount / total * 100):.1f}"]
                            for r in rep.rows
                        ],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 6: Top Merchants ───────────────────────────────────────────────────


def _register_top_merchants() -> None:
    @ui.page("/reports/top-merchants")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {
            "start": (today - datetime.timedelta(days=30)).isoformat(),
            "end": today.isoformat(),
            "data": None,
        }

        with page_layout(t("reports_lib.top_merchants")):
            _report_header(t("reports_lib.top_merchants"), t("reports_lib.top_merchants_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).top_merchants(
                        datetime.date.fromisoformat(state["start"]),
                        datetime.date.fromisoformat(state["end"]) + datetime.timedelta(days=1),
                        limit=20,
                    )
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                ui.input(
                    t("transactions.date_from"), value=state["start"],
                    on_change=lambda e: (
                        state.update(start=e.value),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).props("type=date").classes("w-44")
                ui.input(
                    t("transactions.date_to"), value=state["end"],
                    on_change=lambda e: (
                        state.update(end=e.value),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).props("type=date").classes("w-44")

            @ui.refreshable
            def output() -> None:
                merchants: list[MerchantSpend] | None = state["data"]
                if merchants is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return
                if not merchants:
                    ui.label(t("reports.no_data")).classes("text-grey-5 py-8")
                    return

                with ui.card().classes(SECTION_CARD):
                    ui.label(t("reports_lib.top_merchants")).classes(SECTION_TITLE)
                    sorted_asc = list(reversed(merchants))
                    ui.echart(
                        apply_dark(
                            {
                                "tooltip": {"trigger": "axis"},
                                "grid": {"left": "3%", "right": "4%", "bottom": "8%",
                                         "containLabel": True},
                                "xAxis": {"type": "value"},
                                "yAxis": {"type": "category",
                                          "data": [m.name for m in sorted_asc]},
                                "series": [{
                                    "name": t("common.amount"),
                                    "type": "bar",
                                    "data": [float(m.amount) for m in sorted_asc],
                                    "itemStyle": {"color": "#009688"},
                                    "label": {"show": True, "position": "right",
                                              "formatter": "{c}"},
                                }],
                            },
                            is_dark,
                        )
                    ).classes("w-full").style(f"height: {max(300, 30 * len(merchants))}px")

                cols = [
                    {"name": "name", "label": t("common.payee"), "field": "name", "align": "left"},
                    {"name": "amount", "label": t("common.amount"), "field": "amount",
                     "align": "right"},
                    {"name": "count", "label": t("reports_lib.transaction_count"),
                     "field": "count", "align": "right"},
                ]
                rows = [
                    {"name": m.name, "amount": _fmt(m.amount), "count": m.count}
                    for m in merchants
                ]
                ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

                def _export() -> None:
                    _csv_download(
                        "top_merchants.csv",
                        [t("common.payee"), t("common.amount"),
                         t("reports_lib.transaction_count")],
                        [[m.name, m.amount, m.count] for m in merchants],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 7: YoY Comparison ──────────────────────────────────────────────────


def _register_yoy() -> None:
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
            _report_header(t("reports_lib.yoy"), t("reports_lib.yoy_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).yoy_comparison(
                        state["year"], TransactionType(state["basis"])
                    )
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
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                total_this = sum((r.this_year for r in rep.rows), Decimal("0"))
                total_last = sum((r.last_year for r in rep.rows), Decimal("0"))
                delta = total_this - total_last

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(str(rep.year), _fmt(total_this), "today", "primary")
                    _kpi(str(rep.year - 1), _fmt(total_last), "history", "grey-7")
                    _kpi(
                        t("reports_lib.delta"),
                        _fmt(delta),
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
                                "legend": {"data": [str(rep.year), str(rep.year - 1)],
                                           "bottom": 0},
                                "grid": {"left": "3%", "right": "4%", "bottom": "12%",
                                         "containLabel": True},
                                "xAxis": {"type": "category", "data": months},
                                "yAxis": {"type": "value"},
                                "series": [
                                    {"name": str(rep.year), "type": "bar",
                                     "data": [float(r.this_year) for r in rep.rows],
                                     "itemStyle": {"color": "#1976d2"}},
                                    {"name": str(rep.year - 1), "type": "bar",
                                     "data": [float(r.last_year) for r in rep.rows],
                                     "itemStyle": {"color": "#bdbdbd"}},
                                ],
                            },
                            is_dark,
                        )
                    ).classes("w-full h-80")

                def _export() -> None:
                    _csv_download(
                        f"yoy_{rep.year}.csv",
                        [t("common.month"), str(rep.year), str(rep.year - 1),
                         t("reports_lib.delta"), "delta_pct"],
                        [
                            [months[r.month - 1], r.this_year, r.last_year, r.delta,
                             _fmt_pct(r.delta_pct)]
                            for r in rep.rows
                        ],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 8: YTD Summary ─────────────────────────────────────────────────────


def _register_ytd_summary() -> None:
    @ui.page("/reports/ytd-summary")
    async def page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        today = datetime.date.today()
        state: dict[str, Any] = {"year": today.year, "data": None}

        with page_layout(t("reports_lib.ytd_summary")):
            _report_header(t("reports_lib.ytd_summary"), t("reports_lib.ytd_summary_desc"))

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).ytd_summary(state["year"])
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
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return

                with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                    _kpi(t("reports_lib.ytd_income"), _fmt(rep.income), "trending_up", "green-7")
                    _kpi(t("reports_lib.ytd_expenses"), _fmt(rep.expenses), "trending_down",
                         "red-7")
                    _kpi(t("reports_lib.ytd_net"), _fmt(rep.net), "account_balance",
                         "green-7" if rep.net >= 0 else "red-7")
                    _kpi(t("reports_lib.savings_rate"), _fmt_pct(rep.savings_rate_pct),
                         "savings", "primary")

                if rep.top_expense_categories:
                    with ui.card().classes(SECTION_CARD):
                        ui.label(t("reports_lib.top_expense_cats")).classes(SECTION_TITLE)
                        ui.echart(
                            apply_dark(
                                {
                                    "tooltip": {"trigger": "item",
                                                "formatter": "{b}: {c} ({d}%)"},
                                    "series": [{
                                        "type": "pie",
                                        "radius": ["30%", "65%"],
                                        "data": [
                                            {"name": c.category, "value": float(c.amount)}
                                            for c in rep.top_expense_categories
                                        ],
                                    }],
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
                        ["category", c.category, c.amount]
                        for c in rep.top_expense_categories
                    ]
                    _csv_download(
                        f"ytd_summary_{rep.year}.csv",
                        ["kind", "label", t("common.amount")],
                        summary_rows + cat_rows,
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 9: Largest Transactions ────────────────────────────────────────────


def _register_largest_transactions() -> None:
    @ui.page("/reports/largest-transactions")
    async def page() -> None:
        state: dict[str, Any] = {"days": 90, "limit": 50, "data": None}

        with page_layout(t("reports_lib.largest_transactions")):
            _report_header(
                t("reports_lib.largest_transactions"),
                t("reports_lib.largest_transactions_desc"),
            )

            async def _load() -> None:
                async with AsyncSessionFactory() as s:
                    state["data"] = await ReportService(s).largest_transactions(
                        days=int(state["days"]), limit=int(state["limit"])
                    )
                output.refresh()

            with ui.row().classes("items-end gap-3 mb-2"):
                ui.select(
                    {30: "30", 90: "90", 180: "180", 365: "365"},
                    label=t("reports_lib.days_back"),
                    value=state["days"],
                    on_change=lambda e: (
                        state.update(days=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")
                ui.select(
                    {25: "25", 50: "50", 100: "100"},
                    label=t("reports_lib.limit"),
                    value=state["limit"],
                    on_change=lambda e: (
                        state.update(limit=int(e.value)),
                        ui.timer(0.01, _load, once=True),
                    ),
                ).classes("w-32")

            @ui.refreshable
            def output() -> None:
                items: list[LargeTransaction] | None = state["data"]
                if items is None:
                    ui.label(t("common.loading")).classes("text-grey-5")
                    return
                if not items:
                    ui.label(t("reports.no_data")).classes("text-grey-5 py-8")
                    return

                cols = [
                    {"name": "date", "label": t("common.date"), "field": "date", "align": "left"},
                    {"name": "type", "label": t("common.type"), "field": "type", "align": "left"},
                    {"name": "account", "label": t("common.account"), "field": "account",
                     "align": "left"},
                    {"name": "category", "label": t("common.category"), "field": "category",
                     "align": "left"},
                    {"name": "desc", "label": t("common.description"), "field": "desc",
                     "align": "left"},
                    {"name": "amount", "label": t("common.amount"), "field": "amount",
                     "align": "right"},
                ]
                rows = [
                    {
                        "date": str(i.date),
                        "type": i.type.value,
                        "account": i.account,
                        "category": i.category,
                        "desc": i.description[:50],
                        "amount": _fmt(i.amount),
                        "type_raw": i.type.value,
                    }
                    for i in items
                ]
                tbl = ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")
                tbl.add_slot(
                    "body-cell-amount",
                    '<q-td :props="props" class="text-right">'
                    "<span :class=\"props.row.type_raw === 'income' ? 'text-positive' : "
                    "'text-negative'\">{{ props.row.amount }}</span></q-td>",
                )

                def _export() -> None:
                    _csv_download(
                        "largest_transactions.csv",
                        [t("common.date"), t("common.type"), t("common.account"),
                         t("common.category"), t("common.description"), t("common.amount")],
                        [[str(i.date), i.type.value, i.account, i.category, i.description,
                          i.amount] for i in items],
                    )

                _export_button(_export)

            output()
            await _load()


# ── Report 10: Net Worth Statement (routes to dedicated page) ────────────────


def _register_net_worth_pointer() -> None:
    """The Net Worth page at /net-worth is already a full statement.

    Rather than duplicating it, this report navigates there and surfaces the
    same CSV export of current asset/liability breakdown for users who find
    it via the Reports library.
    """

    @ui.page("/reports/net-worth-statement")
    async def page() -> None:
        from kaleta.services.net_worth_service import NetWorthService

        default_currency: str = app.storage.user.get("currency", "PLN")
        async with AsyncSessionFactory() as s:
            summary = await NetWorthService(s).get_summary(
                history_months=13, default_currency=default_currency
            )

        with page_layout(t("reports_lib.net_worth_statement")):
            _report_header(
                t("reports_lib.net_worth_statement"),
                t("reports_lib.net_worth_statement_desc"),
            )

            with ui.row().classes("w-full gap-3 flex-wrap mb-3"):
                _kpi(t("net_worth.total_assets"), _fmt(summary.total_assets), "trending_up",
                     "green-7")
                _kpi(t("net_worth.total_liabilities"), _fmt(summary.total_liabilities),
                     "trending_down", "red-7")
                _kpi(
                    t("net_worth.net_worth"),
                    _fmt(summary.net_worth),
                    "account_balance",
                    "green-7" if summary.net_worth >= 0 else "red-7",
                )

            cols = [
                {"name": "name", "label": t("common.account"), "field": "name", "align": "left"},
                {"name": "kind", "label": t("common.type"), "field": "kind", "align": "left"},
                {"name": "balance", "label": t("common.balance"), "field": "balance",
                 "align": "right"},
            ]
            rows = [
                {
                    "name": a.name,
                    "kind": t("reports_lib.asset") if a.is_asset else t("reports_lib.liability"),
                    "balance": _fmt(a.balance_in_default),
                }
                for a in summary.accounts
            ]
            ui.table(columns=cols, rows=rows).classes(TABLE_SURFACE).props("flat dense")

            ui.button(
                t("net_worth.title"),
                icon="open_in_new",
                on_click=lambda: ui.navigate.to("/net-worth"),
            ).props("flat color=primary")

            def _export() -> None:
                _csv_download(
                    "net_worth_statement.csv",
                    [t("common.account"), t("common.type"), t("common.balance")],
                    [
                        [
                            a.name,
                            "asset" if a.is_asset else "liability",
                            a.balance_in_default,
                        ]
                        for a in summary.accounts
                    ],
                )

            _export_button(_export)


# ── UI helpers ────────────────────────────────────────────────────────────────


def _kpi(title: str, value: str, icon: str, icon_color: str) -> None:
    with ui.card().classes("flex-1 min-w-44 p-4"), ui.row().classes("items-center gap-3"):
        ui.icon(icon, size="2rem").classes(f"text-{icon_color}")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-xs text-grey-6 uppercase tracking-wide")
            ui.label(value).classes("text-xl font-bold")


def _render_category_table(
    title: str,
    rows_data: list[Any],
    colour: str,
) -> None:
    with ui.card().classes("flex-1 min-w-72 p-0"):
        with ui.row().classes("items-center gap-2 px-4 py-3 border-b"):
            ui.icon("label", color=colour).classes("text-xl")
            ui.label(title).classes("text-base font-semibold flex-1")
        if not rows_data:
            ui.label(t("common.none")).classes("text-grey-5 text-sm px-4 py-2")
            return
        cols = [
            {"name": "category", "label": t("common.category"), "field": "category",
             "align": "left"},
            {"name": "amount", "label": t("common.amount"), "field": "amount", "align": "right"},
        ]
        table_rows = [
            {"category": r.category, "amount": _fmt(r.amount)} for r in rows_data
        ]
        ui.table(columns=cols, rows=table_rows).classes("w-full").props("flat dense")


def _export_button(on_click: Any) -> None:
    with ui.row().classes("justify-end w-full mt-3"):
        ui.button(t("reports_lib.export_csv"), icon="download", on_click=on_click).props(
            "outline color=primary"
        )


# ── Registration ──────────────────────────────────────────────────────────────


def register() -> None:
    _register_landing()
    _register_income_statement()
    _register_cash_flow()
    _register_budget_variance()
    _register_savings_rate()
    _register_spending_by_category()
    _register_top_merchants()
    _register_yoy()
    _register_ytd_summary()
    _register_largest_transactions()
    _register_net_worth_pointer()
