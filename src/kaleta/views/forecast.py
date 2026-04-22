from __future__ import annotations

import datetime
from typing import Any

from nicegui import app, ui

from kaleta.db import AsyncSessionFactory
from kaleta.i18n import t
from kaleta.services.forecast_service import (
    ForecastPreset,
    ForecastResult,
    ForecastService,
    ScenarioShift,
    apply_preset,
    apply_scenarios,
)
from kaleta.views.chart_utils import apply_dark
from kaleta.views.layout import page_layout


def _forecast_chart(
    result: ForecastResult,
    is_dark: bool = False,
    baseline: ForecastResult | None = None,
) -> dict[str, Any]:
    today_str = str(datetime.date.today())

    hist = [(str(p.date), p.value) for p in result.historical]
    fore = [(str(p.date), p.value) for p in result.forecast]
    upper = [(str(p.date), p.upper) for p in result.forecast]
    lower = [(str(p.date), p.lower) for p in result.forecast]
    base_fore = (
        [(str(p.date), p.value) for p in baseline.forecast] if baseline else []
    )

    legend_data = [
        t("forecast.actual"),
        t("forecast.predicted"),
        t("forecast.confidence_band"),
    ]
    if base_fore:
        legend_data.append(t("forecast.baseline_reference"))

    _opts = {
        "tooltip": {"trigger": "axis", "formatter": "{b}<br/>{a0}: {c0} zł"},
        "legend": {
            "data": legend_data,
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

    if base_fore:
        _opts["series"].append(  # type: ignore[attr-defined]
            {
                "name": t("forecast.baseline_reference"),
                "type": "line",
                "data": [None] * len(hist) + [v for _, v in base_fore],
                "itemStyle": {"color": "#9e9e9e"},
                "lineStyle": {"width": 1, "type": "dotted", "color": "#9e9e9e"},
                "showSymbol": False,
                "z": 2,
            }
        )

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

            preset_options: dict[str, str] = {
                ForecastPreset.CONSERVATIVE.value: t("forecast.preset_conservative"),
                ForecastPreset.BASELINE.value: t("forecast.preset_baseline"),
                ForecastPreset.OPTIMISTIC.value: t("forecast.preset_optimistic"),
            }
            saved_preset = app.storage.user.get(
                "forecast_preset", ForecastPreset.BASELINE.value
            )
            if saved_preset not in preset_options:
                saved_preset = ForecastPreset.BASELINE.value

            # User scenario list — each element: {label, date (ISO), amount}.
            raw_scenarios = app.storage.user.get("forecast_scenarios", [])
            scenarios: list[dict[str, Any]] = list(raw_scenarios) if isinstance(
                raw_scenarios, list
            ) else []

            # Controls
            with ui.card().classes("w-full"):
                with ui.row().classes("items-end gap-4 flex-wrap"):
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
                    preset_toggle = ui.toggle(
                        preset_options, value=saved_preset
                    ).props("color=primary")
                    run_btn = ui.button(t("forecast.run"), icon="insights").props(
                        "color=primary"
                    )

                def _persist_preset() -> None:
                    app.storage.user["forecast_preset"] = preset_toggle.value

                preset_toggle.on_value_change(lambda _: _persist_preset())

                # Scenario chips + add control.
                ui.separator().classes("my-3")
                ui.label(t("forecast.scenarios_title")).classes(
                    "text-sm text-grey-6 mb-1"
                )
                scenario_row = ui.row().classes("items-center gap-2 flex-wrap")

                def _render_scenarios() -> None:
                    scenario_row.clear()
                    with scenario_row:
                        if not scenarios:
                            ui.label(t("forecast.scenarios_empty")).classes(
                                "text-xs text-grey-5"
                            )
                        for idx, s in enumerate(scenarios):
                            amt = float(s.get("amount", 0))
                            sign = "+" if amt >= 0 else ""
                            chip_color = "green-7" if amt >= 0 else "red-7"
                            chip = ui.chip(
                                f"{s.get('label', '—')} · {s.get('date', '')} · "
                                f"{sign}{amt:,.0f} zł",
                                icon="bolt",
                                color=chip_color,
                                removable=True,
                            ).props("text-color=white")

                            def _remove(_: Any, i: int = idx) -> None:
                                scenarios.pop(i)
                                app.storage.user["forecast_scenarios"] = scenarios
                                _render_scenarios()

                            chip.on("remove", _remove)

                        ui.button(
                            t("forecast.scenario_add"),
                            icon="add",
                            on_click=lambda: _open_add_scenario_dialog(),
                        ).props("flat dense color=primary")

                def _open_add_scenario_dialog() -> None:
                    today_iso = datetime.date.today().isoformat()
                    with ui.dialog() as dialog, ui.card():
                        ui.label(t("forecast.scenario_add")).classes(
                            "text-lg font-semibold"
                        )
                        label_input = ui.input(t("forecast.scenario_label")).classes(
                            "w-full"
                        )
                        date_input = ui.input(
                            t("common.date"), value=today_iso
                        ).props('type=date').classes("w-full")
                        amount_input = ui.number(
                            t("forecast.scenario_amount"),
                            value=0,
                            format="%.2f",
                        ).classes("w-full")

                        def _save() -> None:
                            label = (label_input.value or "").strip()
                            raw_date = (date_input.value or "").strip()
                            raw_amt = amount_input.value
                            if not label or not raw_date or raw_amt in (None, ""):
                                ui.notify(
                                    t("forecast.scenario_incomplete"), color="negative"
                                )
                                return
                            try:
                                datetime.date.fromisoformat(raw_date)
                                amt_float = float(raw_amt)
                            except (TypeError, ValueError):
                                ui.notify(
                                    t("forecast.scenario_incomplete"), color="negative"
                                )
                                return
                            scenarios.append(
                                {"label": label, "date": raw_date, "amount": amt_float}
                            )
                            app.storage.user["forecast_scenarios"] = scenarios
                            _render_scenarios()
                            dialog.close()

                        with ui.row().classes("justify-end gap-2 w-full mt-2"):
                            ui.button(t("common.cancel"), on_click=dialog.close).props(
                                "flat"
                            )
                            ui.button(
                                t("common.save"), icon="check", on_click=_save
                            ).props("color=primary")
                    dialog.open()

                _render_scenarios()

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
                    raw = await ForecastService(session).forecast_account(
                        account_id=acct_id, horizon_days=horizon
                    )

                run_btn.props(remove="loading")

                if raw.insufficient_data or not raw.points:
                    status.set_text(t("forecast.insufficient"))
                    return

                shifts: list[ScenarioShift] = []
                for s in scenarios:
                    try:
                        shifts.append(
                            ScenarioShift(
                                label=str(s.get("label", "")),
                                date=datetime.date.fromisoformat(str(s.get("date", ""))),
                                amount=float(s.get("amount", 0)),
                            )
                        )
                    except (TypeError, ValueError):
                        continue

                preset = ForecastPreset(preset_toggle.value or ForecastPreset.BASELINE.value)
                result = apply_scenarios(apply_preset(raw, preset), shifts)
                baseline = (
                    apply_scenarios(raw, shifts)
                    if preset is not ForecastPreset.BASELINE
                    else None
                )

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
                        ui.echart(
                            _forecast_chart(result, is_dark, baseline=baseline)
                        ).classes("w-full h-96")

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
