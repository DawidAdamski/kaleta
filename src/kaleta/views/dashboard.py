from __future__ import annotations

from decimal import Decimal

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.models.transaction import TransactionType
from kaleta.services import ReportService
from kaleta.services.forecast_service import ForecastService
from kaleta.services.report_service import MonthCashflow
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout


def _fmt(amount: Decimal) -> str:
    return f"{amount:,.2f} zł"


def _cashflow_chart_options(months: list[MonthCashflow], is_dark: bool = False) -> dict:
    _opts = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": ["Income", "Expenses", "Net"], "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": [m.label for m in months],
        },
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "series": [
            {
                "name": "Income",
                "type": "bar",
                "stack": "cashflow",
                "data": [float(m.income) for m in months],
                "itemStyle": {"color": "#4caf50"},
            },
            {
                "name": "Expenses",
                "type": "bar",
                "stack": "cashflow",
                "data": [-float(m.expenses) for m in months],
                "itemStyle": {"color": "#ef5350"},
            },
            {
                "name": "Net",
                "type": "line",
                "data": [float(m.net) for m in months],
                "itemStyle": {"color": "#1976d2"},
                "lineStyle": {"width": 2},
                "symbol": "circle",
                "symbolSize": 6,
            },
        ],
    }
    return apply_dark(_opts, is_dark)


def register() -> None:
    @ui.page("/")
    async def dashboard() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        async with AsyncSessionFactory() as session:
            svc = ReportService(session)
            total_balance = await svc.total_balance()
            income, expenses = await svc.current_month_summary()
            cashflow = await svc.cashflow_last_n_months(6)
            recent = await svc.recent_transactions(10)
            forecast_result = await ForecastService(session).forecast_account(
                account_id=None, horizon_days=30
            )

        net = income - expenses
        net_color = "text-green-700" if net >= 0 else "text-red-700"
        pred_30 = forecast_result.predicted_balance_30d

        with page_layout("Dashboard"):
            ui.label("Dashboard").classes("text-2xl font-bold")

            # ── KPI cards ────────────────────────────────────────────────────
            with ui.row().classes("w-full gap-4 flex-wrap"):
                _kpi("Total Balance",   _fmt(total_balance), "account_balance",    "blue-7")
                _kpi("Month Income",    _fmt(income),        "trending_up",        "green-7")
                _kpi("Month Expenses",  _fmt(expenses),      "trending_down",      "red-7")
                _kpi("Month Net",       _fmt(net),           "swap_vert",          "orange-7", extra_cls=net_color)
                if pred_30 is not None:
                    pred_color = "green-7" if pred_30 >= float(total_balance) else "red-7"
                    _kpi(
                        f"Balance in 30 days",
                        f"{pred_30:,.2f} zł",
                        "insights",
                        pred_color,
                    )

            # ── Cashflow chart ───────────────────────────────────────────────
            with ui.card().classes("w-full"):
                ui.label("Cashflow — last 6 months").classes("text-lg font-semibold mb-2")
                ui.echart(_cashflow_chart_options(cashflow, is_dark)).classes("w-full h-72")

            # ── Recent transactions ──────────────────────────────────────────
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between mb-2"):
                    ui.label("Recent Transactions").classes("text-lg font-semibold")
                    ui.button("View All", on_click=lambda: ui.navigate.to("/transactions")).props("flat dense")

                if not recent:
                    ui.label("No transactions yet. Press Ctrl+N to add one.").classes("text-grey-6")
                else:
                    columns = [
                        {"name": "date",     "label": "Date",        "field": "date",     "align": "left"},
                        {"name": "account",  "label": "Account",     "field": "account",  "align": "left"},
                        {"name": "desc",     "label": "Description", "field": "desc",     "align": "left"},
                        {"name": "category", "label": "Category",    "field": "category", "align": "left"},
                        {"name": "amount",   "label": "Amount",      "field": "amount",   "align": "right"},
                    ]
                    rows = [
                        {
                            "date":     str(t.date),
                            "account":  t.account.name if t.account else "—",
                            "desc":     (t.description or "—")[:45],
                            "category": t.category.name if t.category else "—",
                            "amount": (
                                f"+{t.amount:,.2f}" if t.type == TransactionType.INCOME
                                else f"-{t.amount:,.2f}"
                            ),
                        }
                        for t in recent
                    ]
                    ui.table(columns=columns, rows=rows).classes("w-full").props("dense flat")


def _kpi(title: str, value: str, icon: str, icon_color: str, extra_cls: str = "") -> None:
    with ui.card().classes("flex-1 min-w-44"):
        with ui.row().classes("items-center gap-3 w-full"):
            ui.icon(icon, size="2.2rem").classes(f"text-{icon_color}")
            with ui.column().classes("gap-0"):
                ui.label(title).classes("text-xs text-grey-6 uppercase tracking-wide")
                ui.label(value).classes(f"text-xl font-bold {extra_cls}")
