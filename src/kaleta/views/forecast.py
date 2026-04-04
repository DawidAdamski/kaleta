from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.services.forecast_service import ForecastResult, ForecastService
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout


def _forecast_chart(result: ForecastResult, is_dark: bool = False) -> dict[str, Any]:
    today_str = str(datetime.date.today())

    hist = [(str(p.date), p.value) for p in result.historical]
    fore = [(str(p.date), p.value) for p in result.forecast]
    upper = [(str(p.date), p.upper) for p in result.forecast]
    lower = [(str(p.date), p.lower) for p in result.forecast]

    _opts = {
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>{a0}: {c0} zł"},
        "legend": {
            "data": [t("forecast.actual"), t("forecast.predicted"), t("forecast.confidence_band")],
            "bottom": 0,
        },
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": [p[0] for p in hist] + [p[0] for p in fore],
            "axisLabel": {"rotate": 30},
            "markLine": {
                "data": [{"xAxis": today_str, "name": t("forecast.today")}],
            },
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "{value} zł"},
        },
        "series": [
            {
                "name": t("forecast.actual"),
                "type": "line",
                "data": [v for _, v in hist],
                "itemStyle": {"color": "#1976d2"},
                "lineStyle": {"width": 2},
                "showSymbol": False,
                "z": 3,
            },
            {
                "name": t("forecast.predicted"),
                "type": "line",
                "data": [None] * len(hist) + [v for _, v in fore],
                "itemStyle": {"color": "#fb8c00"},
                "lineStyle": {"width": 2, "type": "dashed"},
                "showSymbol": False,
                "z": 3,
            },
            {
                "name": t("forecast.upper"),
                "type": "line",
                "data": [None] * len(hist) + [v for _, v in upper],
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "z": 1,
            },
            {
                "name": t("forecast.confidence_band"),
                "type": "line",
                "data": [None] * len(hist)
                + [
                    upper_value - lower_value
                    for (_, upper_value), (_, lower_value) in zip(upper, lower, strict=True)
                ],
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "areaStyle": {"color": "#fb8c00", "opacity": 0.15},
                "z": 1,
            },
        ],
    }
    return apply_dark(_opts, is_dark)


def register() -> None:
    @ui.page("/forecast")
    async def forecast_page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)
        async with AsyncSessionFactory() as session:
            accounts = await ForecastService(session).available_accounts()

        account_options: dict[int | str, str] = {"all": t("forecast.all_accounts")}
        account_options.update({a.id: a.name for a in accounts})

        with page_layout(t("forecast.title")):
            ui.label(t("forecast.chart_title")).classes("text-2xl font-bold")

            # Controls
            with ui.card().classes("w-full"), ui.row().classes("items-end gap-4 flex-wrap"):
                account_sel = ui.select(
                    account_options, label=t("forecast.account"), value="all"
                ).classes("min-w-52")
                horizon_sel = ui.select(
                    {
                        30: t("forecast.days_30"),
                        60: t("forecast.days_60"),
                        90: t("forecast.days_90"),
                    },
                    label=t("forecast.horizon"),
                    value=60,
                ).classes("min-w-36")
                run_btn = ui.button(t("forecast.run"), icon="insights").props("color=primary")

            # Output area
            status = ui.label(t("forecast.click_run")).classes("text-grey-6 text-sm")
            chart_container = ui.column().classes("w-full")
            kpi_row = ui.row().classes("w-full gap-4 flex-wrap")

            async def run_forecast() -> None:
                chart_container.clear()
                kpi_row.clear()
                status.set_text(t("forecast.running"))
                run_btn.props("loading")

                chosen = account_sel.value
                acct_id = None if chosen == "all" else int(chosen)
                horizon = int(horizon_sel.value)

                async with AsyncSessionFactory() as session:
                    result = await ForecastService(session).forecast_account(
                        account_id=acct_id, horizon_days=horizon
                    )

                run_btn.props(remove="loading")

                if result.insufficient_data or not result.points:
                    status.set_text(t("forecast.insufficient"))
                    return

                status.set_text(
                    t(
                        "forecast.status_running",
                        account=result.account_name,
                        days=len(result.historical),
                        horizon=horizon,
                    )
                )

                # KPI cards
                with kpi_row:
                    today_balance = next((p.value for p in reversed(result.historical)), None)
                    pred_30 = result.predicted_balance_30d

                    if today_balance is not None:
                        _kpi(
                            kpi_row,
                            t("forecast.current_balance"),
                            f"{today_balance:,.2f} zł",
                            "account_balance",
                            "blue-7",
                        )
                    if pred_30 is not None:
                        color = "green-7" if pred_30 >= (today_balance or 0) else "red-7"
                        _kpi(
                            kpi_row,
                            t("forecast.predicted_30"),
                            f"{pred_30:,.2f} zł",
                            "trending_flat",
                            color,
                        )
                        if today_balance is not None:
                            delta = pred_30 - today_balance
                            sign = "+" if delta >= 0 else ""
                            delta_color = "green-7" if delta >= 0 else "red-7"
                            _kpi(
                                kpi_row,
                                t("forecast.change_30"),
                                f"{sign}{delta:,.2f} zł",
                                "swap_vert",
                                delta_color,
                            )

                with chart_container:
                    with ui.card().classes("w-full"):
                        ui.label(
                            t("forecast.chart_title_account", account=result.account_name)
                        ).classes("text-lg font-semibold mb-2")
                        ui.echart(_forecast_chart(result, is_dark)).classes("w-full h-96")

                    with ui.card().classes("w-full"):
                        ui.label(t("forecast.upcoming_14")).classes("text-lg font-semibold mb-2")
                        upcoming = result.forecast[:14]
                        columns = [
                            {
                                "name": "date",
                                "label": t("common.date"),
                                "field": "date",
                                "align": "left",
                            },
                            {
                                "name": "yhat",
                                "label": t("forecast.predicted"),
                                "field": "yhat",
                                "align": "right",
                            },
                            {
                                "name": "lower",
                                "label": t("forecast.lower_ci"),
                                "field": "lower",
                                "align": "right",
                            },
                            {
                                "name": "upper",
                                "label": t("forecast.upper_ci"),
                                "field": "upper",
                                "align": "right",
                            },
                        ]
                        rows = [
                            {
                                "date": str(p.date),
                                "yhat": f"{p.value:,.2f} zł",
                                "lower": f"{p.lower:,.2f} zł",
                                "upper": f"{p.upper:,.2f} zł",
                            }
                            for p in upcoming
                        ]
                        ui.table(columns=columns, rows=rows).classes("w-full").props("flat dense")

                    # Planned transactions card
                    if result.planned_occurrences:
                        with ui.card().classes("w-full"):
                            ui.label(t("forecast.planned_in_period")).classes(
                                "text-lg font-semibold mb-2"
                            )
                            p_cols = [
                                {
                                    "name": "date",
                                    "label": t("common.date"),
                                    "field": "date",
                                    "align": "left",
                                },
                                {
                                    "name": "name",
                                    "label": t("planned.name"),
                                    "field": "name",
                                    "align": "left",
                                },
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
                            ]
                            p_rows = [
                                {
                                    "date": str(occ.date),
                                    "name": occ.name,
                                    "category": occ.category_name or "—",
                                    "amount": (
                                        f"+{occ.amount:,.2f} zł"
                                        if occ.type.value == "income"
                                        else f"-{occ.amount:,.2f} zł"
                                    ),
                                    "type": occ.type.value,
                                }
                                for occ in result.planned_occurrences
                            ]
                            p_tbl = (
                                ui.table(columns=p_cols, rows=p_rows)
                                .classes("w-full")
                                .props("flat dense")
                            )
                            p_tbl.add_slot(
                                "body-cell-amount",
                                '<q-td :props="props" class="text-right">'
                                "<span :class=\"props.row.type === 'income'"
                                " ? 'text-positive' : 'text-negative'\">"
                                "{{ props.row.amount }}</span></q-td>",
                            )

            run_btn.on("click", run_forecast)


def _kpi(parent: ui.row, title: str, value: str, icon: str, icon_color: str) -> None:
    with parent, ui.card().classes("flex-1 min-w-44"), ui.row().classes("items-center gap-3"):
        ui.icon(icon, size="2rem").classes(f"text-{icon_color}")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-xs text-grey-6 uppercase tracking-wide")
            ui.label(value).classes("text-xl font-bold")
