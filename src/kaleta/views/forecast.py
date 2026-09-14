# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Any

from nicegui import app, ui

from kaleta.i18n import t
from kaleta.services import with_session
from kaleta.services.forecast_service import (
    ForecastKpis,
    ForecastPreset,
    ForecastResult,
    ForecastService,
    ScenarioShift,
    apply_preset,
    apply_scenarios,
    forecast_kpis,
)
from kaleta.services.forecasters import is_prophet_available
from kaleta.views.chart_utils import (
    CHART_BAND,
    CHART_NEUTRAL_BAR,
    apply_dark,
    chart_accent_color,
    chart_accent_fill,
    chart_grid_color,
    chart_ink_color,
    chart_text_color,
)
from kaleta.views.components.amount_label import format_signed_amount, net_tone
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    ACCENT_SOFT,
    BODY_MUTED,
    DIALOG_TITLE,
    FILTER_CHIP,
    FILTER_CHIP_EMPTY,
    KPI_VALUE,
    MONO,
    MUTED,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
    SECTION_TITLE,
    SKELETON,
    TABLE_SURFACE,
    amount_class,
    kpi_card_classes,
)


def _forecast_chart(
    result: ForecastResult,
    is_dark: bool = False,
    baseline: ForecastResult | None = None,
    scenarios: list[ScenarioShift] | None = None,
) -> dict[str, Any]:
    """One chart: what happened, what is predicted, and how sure that is.

    The x-axis is ``time``, not ``category``. A category axis spaces points
    evenly whichever dates they carry, so ninety days of history drawn beside
    sixty daily forecast points came out compressed — the past looked like it
    happened faster than the future. A time axis puts every point where its
    date belongs.
    """
    today = datetime.date.today()
    scenarios = scenarios or []

    hist = [[str(p.date), p.value] for p in result.historical]
    fore = [[str(p.date), p.value] for p in result.forecast]
    lower = [[str(p.date), p.lower] for p in result.forecast]
    # The band is drawn by stacking its height on top of its floor, so the
    # floor is the *lower* bound: stacking on the upper one would have put the
    # whole band above the prediction it is supposed to surround.
    band = [[str(p.date), round(p.upper - p.lower, 2)] for p in result.forecast]
    base_fore = [[str(p.date), p.value] for p in baseline.forecast] if baseline else []

    # The prediction starts where the history stops, so the two lines meet
    # instead of leaving a day-wide gap at today.
    if hist and fore:
        fore = [hist[-1], *fore]

    accent = chart_accent_color(is_dark)
    grid_color = chart_grid_color(is_dark)
    # The plan's colours exactly: #EFCDB2 in light, and in dark the accent at
    # 0.18 — which `chart_accent_fill` already carries as an rgba, so neither
    # needs an opacity of its own.
    band_color = chart_accent_fill(is_dark) if is_dark else CHART_BAND

    legend_data = [
        t("forecast.actual"),
        t("forecast.predicted"),
        t("forecast.confidence_band"),
    ]
    if base_fore:
        legend_data.append(t("forecast.baseline_reference"))

    mark_lines: list[dict[str, Any]] = [
        {
            "xAxis": str(today),
            "name": t("forecast.today"),
            "label": {"formatter": t("forecast.today"), "color": chart_text_color(is_dark)},
        }
    ]
    mark_points: list[dict[str, Any]] = []
    forecast_by_date = {p.date: p.value for p in result.forecast}
    for shift in scenarios:
        mark_lines.append(
            {
                "xAxis": str(shift.date),
                "name": shift.label,
                "label": {"formatter": shift.label, "color": accent},
                "lineStyle": {"color": accent, "type": "dotted"},
            }
        )
        value = forecast_by_date.get(shift.date)
        if value is not None:
            mark_points.append(
                {"coord": [str(shift.date), value], "name": shift.label, "value": shift.label}
            )

    _opts: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": legend_data, "bottom": 0},
        "grid": {"left": "3%", "right": "4%", "bottom": "12%", "containLabel": True},
        "xAxis": {"type": "time"},
        "yAxis": {"type": "value", "axisLabel": {"formatter": "{value} zł"}},
        "series": [
            {
                "name": t("forecast.lower"),
                "type": "line",
                "data": lower,
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "silent": True,
                "z": 1,
            },
            {
                "name": t("forecast.confidence_band"),
                "type": "line",
                "data": band,
                "lineStyle": {"opacity": 0},
                "showSymbol": False,
                "stack": "confidence",
                "areaStyle": {"color": band_color},
                "z": 1,
            },
            {
                "name": t("forecast.actual"),
                "type": "line",
                "data": hist,
                "itemStyle": {"color": chart_ink_color(is_dark)},
                "lineStyle": {"width": 2},
                "showSymbol": False,
                "z": 3,
            },
            {
                "name": t("forecast.predicted"),
                "type": "line",
                "data": fore,
                "itemStyle": {"color": accent},
                "lineStyle": {"width": 2, "type": "dashed"},
                "showSymbol": False,
                "z": 3,
                "markLine": {
                    "symbol": "none",
                    "silent": True,
                    "lineStyle": {"color": grid_color, "type": "dashed"},
                    "data": mark_lines,
                },
                "markPoint": {
                    "symbol": "pin",
                    "symbolSize": 34,
                    "itemStyle": {"color": accent},
                    "label": {"show": False},
                    "data": mark_points,
                },
            },
        ],
    }

    if base_fore:
        _opts["series"].append(
            {
                "name": t("forecast.baseline_reference"),
                "type": "line",
                "data": base_fore,
                "itemStyle": {"color": CHART_NEUTRAL_BAR},
                "lineStyle": {"width": 1, "type": "dotted", "color": CHART_NEUTRAL_BAR},
                "showSymbol": False,
                "z": 2,
            }
        )

    return apply_dark(_opts, is_dark)


logger = logging.getLogger(__name__)

#: How long a control change waits before it re-runs itself.
_DEBOUNCE_SECONDS = 0.3

#: Where the Prophet footnote points.
_PROPHET_DOCS_URL = "https://github.com/DawidAdamski/kaleta#optional-forecasting"

_HORIZONS = (30, 60, 90)


def _saved_horizon() -> int:
    raw = app.storage.user.get("forecast_horizon", 60)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 60
    return value if value in _HORIZONS else 60


def _saved_account(options: dict[int | str, str]) -> int | str:
    raw = app.storage.user.get("forecast_account", "all")
    if raw in options:
        return raw  # type: ignore[no-any-return]
    try:
        as_int = int(raw)
    except (TypeError, ValueError):
        return "all"
    return as_int if as_int in options else "all"


def _scenario_shifts(scenarios: list[dict[str, Any]]) -> list[ScenarioShift]:
    """The stored scenarios that are still readable, as the service wants them.

    Storage is a user-editable blob; a half-written entry should cost its own
    marker, not the whole forecast.
    """
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
    return shifts


def register() -> None:
    @ui.page("/forecast")
    async def forecast_page() -> None:
        is_dark: bool = app.storage.user.get("dark_mode", False)

        async def _load_accounts(session: Any) -> dict[int | str, str]:
            accounts = await ForecastService(session).available_accounts()
            options: dict[int | str, str] = {"all": t("forecast.all_accounts")}
            options.update({a.id: a.name for a in accounts})
            return options

        account_options = await with_session(_load_accounts)
        prophet_available = is_prophet_available()

        preset_options: dict[str, str] = {
            ForecastPreset.CONSERVATIVE.value: t("forecast.preset_conservative"),
            ForecastPreset.BASELINE.value: t("forecast.preset_baseline"),
            ForecastPreset.OPTIMISTIC.value: t("forecast.preset_optimistic"),
        }
        saved_preset = app.storage.user.get("forecast_preset", ForecastPreset.BASELINE.value)
        if saved_preset not in preset_options:
            saved_preset = ForecastPreset.BASELINE.value

        # User scenario list — each element: {label, date (ISO), amount}.
        raw_scenarios = app.storage.user.get("forecast_scenarios", [])
        scenarios: list[dict[str, Any]] = (
            list(raw_scenarios) if isinstance(raw_scenarios, list) else []
        )

        with page_layout(t("forecast.title")):
            # Title row: the page says what it is on the left, and everything
            # that changes the answer sits on the right — so the first thing
            # below is the answer itself, not an empty frame and a button.
            with ui.row().classes("w-full items-center justify-between gap-4 flex-wrap"):
                ui.label(t("forecast.chart_title")).classes(PAGE_TITLE)
                with ui.row().classes("items-center gap-2 flex-wrap"):
                    account_sel = (
                        ui.select(account_options, value=_saved_account(account_options))
                        .props("dense outlined options-dense")
                        .classes("min-w-44")
                    )
                    account_sel.props["aria-label"] = t("forecast.account")
                    horizon_sel = (
                        ui.select(
                            {d: t(f"forecast.days_{d}") for d in _HORIZONS},
                            value=_saved_horizon(),
                        )
                        .props("dense outlined options-dense")
                        .classes("min-w-32")
                    )
                    horizon_sel.props["aria-label"] = t("forecast.horizon")
                    preset_toggle = None
                    if prophet_available:
                        preset_toggle = ui.toggle(preset_options, value=saved_preset).props(
                            "dense no-caps color=primary"
                        )
                    run_btn = ui.button(t("forecast.rerun"), icon="refresh").props(
                        "flat dense no-caps color=primary"
                    )

            status = ui.label("").classes(BODY_MUTED)
            kpi_row = ui.row().classes("w-full gap-4 flex-wrap")
            chart_container = ui.column().classes("w-full gap-6")

            with ui.card().classes(f"{SECTION_CARD} w-full"):
                ui.label(t("forecast.scenarios_title")).classes(SECTION_TITLE)
                scenario_row = ui.row().classes("items-center gap-2 flex-wrap mt-2")

            #: What the last run returned, so a preset or a scenario can be
            #: applied to it without asking the forecaster again.
            _run_state: dict[str, Any] = {"raw": None, "horizon": 60, "running": False}

            def _mark_stale() -> None:
                """Prophet runs are slow, so a change asks before spending one."""
                status.set_text(t("forecast.stale_hint"))
                run_btn.props(add="color=primary", remove="flat")

            def _on_controls_changed() -> None:
                """The account or the horizon changed — that needs a new run."""
                app.storage.user["forecast_account"] = account_sel.value
                app.storage.user["forecast_horizon"] = horizon_sel.value
                if prophet_available:
                    _mark_stale()
                else:
                    _debounced_run()

            def _on_preset_changed() -> None:
                """A preset leans on bands the forecaster already produced.

                It is `apply_preset` over the run in hand, so it redraws at
                once whichever forecaster is installed — there is nothing to
                wait for, and nothing to mark stale.
                """
                if preset_toggle is not None:
                    app.storage.user["forecast_preset"] = preset_toggle.value
                if not _redraw_from_last_run():
                    _debounced_run()

            async def _debounce_tick() -> None:
                debounce.deactivate()
                await run_forecast()

            # One timer, built with the page and armed by a change rather than
            # a fresh timer per change: a handler's ambient slot can be gone by
            # the time it runs (the chip that opened a dialog is redrawn by the
            # dialog's own Save), and a timer created there dies with it.
            debounce = ui.timer(_DEBOUNCE_SECONDS, _debounce_tick, active=False)

            def _debounced_run() -> None:
                """Coalesce a flurry of control changes into one run.

                Without it, arrowing through a select's options starts a
                forecast per keystroke, and the last one to *finish* — not the
                last one asked for — wins.
                """
                debounce.activate()

            def _render_scenarios() -> None:
                scenario_row.clear()
                with scenario_row:
                    if not scenarios:
                        ui.label(t("forecast.scenarios_empty")).classes(f"{MUTED} text-xs")
                    for idx, s in enumerate(scenarios):
                        amt = float(s.get("amount", 0))
                        label = str(s.get("label", "—"))
                        with ui.row().classes(f"{FILTER_CHIP} gap-2"):
                            ui.label(f"{label} · {s.get('date', '')}").classes("text-xs")
                            ui.label(f"{amt:+,.0f} zł").classes(
                                f"{MONO} text-xs {net_tone(Decimal(str(amt)))}"
                            )
                            remove = ui.icon("close", size="14px").classes("cursor-pointer")
                            remove.props["aria-label"] = t("forecast.scenario_remove", label=label)

                            def _remove(_: Any, i: int = idx) -> None:
                                scenarios.pop(i)
                                app.storage.user["forecast_scenarios"] = scenarios
                                _render_scenarios()
                                _on_scenarios_changed()

                            remove.on("click", _remove)

                    add = ui.row().classes(f"{FILTER_CHIP} {FILTER_CHIP_EMPTY} gap-1")
                    with add:
                        ui.icon("add", size="14px")
                        ui.label(t("forecast.scenario_add")).classes("text-xs")
                    add.on("click", lambda: _open_add_scenario_dialog())

            def _on_scenarios_changed() -> None:
                """A scenario never costs a forecast.

                ``apply_scenarios`` shifts the series that has already been
                computed, so the figures and the chart can be redrawn from the
                run in hand. Sending this down the stale/Re-run path would
                have meant adding a windfall and watching nothing move, which
                is the opposite of what KAL-FCT-011 promises.
                """
                if not _redraw_from_last_run():
                    _debounced_run()

            def _save_scenario() -> None:
                label = (label_input.value or "").strip()
                raw_date = (date_input.value or "").strip()
                raw_amt = amount_input.value
                if not label or not raw_date or raw_amt in (None, ""):
                    ui.notify(t("forecast.scenario_incomplete"), color="negative")
                    return
                try:
                    datetime.date.fromisoformat(raw_date)
                    amt_float = float(raw_amt)
                except (TypeError, ValueError):
                    ui.notify(t("forecast.scenario_incomplete"), color="negative")
                    return
                scenarios.append({"label": label, "date": raw_date, "amount": amt_float})
                app.storage.user["forecast_scenarios"] = scenarios
                add_dialog.close()
                _render_scenarios()
                _on_scenarios_changed()

            # Built with the page rather than inside the chip that opens it:
            # Save redraws the chips, and a dialog living among them would be
            # deleted halfway through its own handler.
            with ui.dialog() as add_dialog, ui.card().classes(SECTION_CARD):
                ui.label(t("forecast.scenario_add")).classes(DIALOG_TITLE)
                label_input = ui.input(t("forecast.scenario_label")).classes("w-full")
                date_input = ui.input(t("common.date")).props("type=date").classes("w-full")
                amount_input = ui.number(
                    t("forecast.scenario_amount"), value=0, format="%.2f"
                ).classes("w-full")
                with ui.row().classes("justify-end gap-2 w-full mt-2"):
                    ui.button(t("common.cancel"), on_click=add_dialog.close).props("flat")
                    ui.button(t("common.save"), icon="check", on_click=_save_scenario).props(
                        "color=primary"
                    )

            def _open_add_scenario_dialog() -> None:
                label_input.value = ""
                date_input.value = datetime.date.today().isoformat()
                amount_input.value = 0
                add_dialog.open()

            def _render_skeleton() -> None:
                chart_container.clear()
                kpi_row.clear()
                with kpi_row:
                    for _ in range(4):
                        ui.skeleton().classes(f"{SKELETON} flex-1 min-w-52 h-24 rounded-xl")
                with chart_container, ui.card().classes(f"{SECTION_CARD} w-full"):
                    ui.skeleton().classes(f"{SKELETON} w-full h-96 rounded-xl")

            async def run_forecast() -> None:
                """Ask the forecaster, then draw what it said.

                One run at a time: the on-load timer, the debounce and the
                Re-run button can all ask at once, and two runs in flight end
                with the last to *finish* on screen rather than the last one
                asked for — the very race the debounce exists to prevent.
                """
                if _run_state["running"]:
                    return
                _run_state["running"] = True
                _render_skeleton()
                status.set_text(
                    t("forecast.running_prophet")
                    if prophet_available
                    else t("forecast.running_naive")
                )
                run_btn.props(add="loading")

                chosen = account_sel.value
                acct_id = None if chosen == "all" else int(chosen)
                horizon = int(horizon_sel.value)

                async def _run_forecast(session: Any) -> Any:
                    return await ForecastService(session).forecast_account(
                        account_id=acct_id, horizon_days=horizon
                    )

                try:
                    raw = await with_session(_run_forecast)
                except Exception:
                    # The skeleton is the whole page now that it draws on
                    # load, so a failure must not leave it standing there.
                    logger.exception("Forecast run failed")
                    chart_container.clear()
                    kpi_row.clear()
                    status.set_text(t("forecast.failed"))
                    return
                finally:
                    run_btn.props(remove="loading")
                    # Whatever the run said, the controls are no longer ahead
                    # of the chart, so the button drops back to its quiet state.
                    run_btn.props(add="flat")
                    _run_state["running"] = False

                _run_state["raw"] = raw
                _run_state["horizon"] = horizon
                if not _redraw_from_last_run():
                    chart_container.clear()
                    kpi_row.clear()
                    status.set_text(t("forecast.insufficient"))

            def _redraw_from_last_run() -> bool:
                """Redraw from the run in hand, with the preset and scenarios on.

                Both are pure post-processing — ``apply_preset`` blends toward
                a band the forecaster already gave us, ``apply_scenarios``
                adds a constant from a date onward — so neither is worth a
                second trip to Prophet. Returns False when there is nothing to
                draw, which is the caller's cue to say why.
                """
                raw = _run_state["raw"]
                if raw is None or raw.insufficient_data or not raw.points:
                    return False

                shifts = _scenario_shifts(scenarios)
                preset_value = (
                    preset_toggle.value
                    if preset_toggle is not None
                    else ForecastPreset.BASELINE.value
                )
                preset = ForecastPreset(preset_value or ForecastPreset.BASELINE.value)
                result = apply_scenarios(apply_preset(raw, preset), shifts)
                baseline = (
                    apply_scenarios(raw, shifts) if preset is not ForecastPreset.BASELINE else None
                )

                status.set_text(
                    t(
                        "forecast.status_running",
                        account=result.account_name,
                        days=len(result.historical),
                        horizon=_run_state["horizon"],
                    )
                )
                _render_kpis(forecast_kpis(result))
                _render_chart(result, baseline, shifts)
                return True

            def _render_kpis(kpis: ForecastKpis) -> None:
                kpi_row.clear()
                with kpi_row:
                    _kpi(
                        "balance_today",
                        t("forecast.kpi_balance_today"),
                        _money(kpis.balance_today),
                        "account_balance",
                    )
                    _kpi(
                        "predicted",
                        t("forecast.kpi_predicted"),
                        _money(kpis.predicted),
                        "trending_flat",
                        hint=(
                            t("forecast.kpi_at_date", date=str(kpis.horizon_date))
                            if kpis.horizon_date
                            else ""
                        ),
                    )
                    change_tone = (
                        net_tone(Decimal(str(kpis.change))) if kpis.change is not None else MUTED
                    )
                    _kpi(
                        "change",
                        t("forecast.kpi_change"),
                        _signed(kpis.change),
                        "swap_vert",
                        value_cls=change_tone,
                    )
                    _kpi(
                        "confidence",
                        t("forecast.kpi_confidence"),
                        "—" if kpis.confidence is None else f"± {kpis.confidence:,.2f} zł",
                        "linear_scale",
                        hint=t("forecast.kpi_confidence_hint"),
                    )

            def _render_chart(
                result: ForecastResult,
                baseline: ForecastResult | None,
                shifts: list[ScenarioShift],
            ) -> None:
                chart_container.clear()
                with chart_container:
                    with ui.card().classes(f"{SECTION_CARD} w-full"):
                        ui.label(
                            t("forecast.chart_title_account", account=result.account_name)
                        ).classes(SECTION_HEADING)
                        if not prophet_available:
                            # A footnote, not an amber banner: the projection
                            # still works, and the page is not an error page.
                            with ui.row().classes("items-center gap-1 mt-0.5"):
                                ui.label(t("forecast.fallback_footnote")).classes(
                                    f"{MUTED} text-xs"
                                )
                                ui.link(
                                    t("forecast.fallback_docs_link"),
                                    _PROPHET_DOCS_URL,
                                    new_tab=True,
                                ).classes("text-xs")
                        ui.echart(
                            _forecast_chart(result, is_dark, baseline=baseline, scenarios=shifts)
                        ).classes("w-full h-96 mt-3")

                    _render_upcoming(result)
                    _render_planned(result)

            def _render_upcoming(result: ForecastResult) -> None:
                with ui.card().classes(f"{SECTION_CARD} w-full"):
                    ui.label(t("forecast.upcoming_14")).classes(SECTION_HEADING)
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
                        for p in result.forecast[:14]
                    ]
                    ui.table(columns=columns, rows=rows).classes(
                        f"{TABLE_SURFACE} {MONO} mt-3"
                    ).props("flat dense")

            def _render_planned(result: ForecastResult) -> None:
                if not result.planned_occurrences:
                    return
                with ui.card().classes(f"{SECTION_CARD} w-full"):
                    ui.label(t("forecast.planned_in_period")).classes(SECTION_HEADING)
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
                            "amount": format_signed_amount(occ.amount, occ.type),
                            "amount_class": amount_class(occ.type.value),
                        }
                        for occ in result.planned_occurrences
                    ]
                    p_tbl = (
                        ui.table(columns=p_cols, rows=p_rows)
                        .classes(f"{TABLE_SURFACE} mt-3")
                        .props("flat dense")
                    )
                    p_tbl.add_slot(
                        "body-cell-amount",
                        '<q-td :props="props" class="text-right">'
                        '<span class="k-mono" :class="props.row.amount_class">'
                        "{{ props.row.amount }}</span></q-td>",
                    )

            _render_scenarios()

            for control in (account_sel, horizon_sel):
                control.on_value_change(lambda _: _on_controls_changed())
            if preset_toggle is not None:
                preset_toggle.on_value_change(lambda _: _on_preset_changed())
            run_btn.on("click", run_forecast)

            # The page answers before it is asked: a forecast is what this
            # page is for, and an empty frame behind a button was a question
            # the user had already answered by navigating here.
            _render_skeleton()
            ui.timer(0.05, run_forecast, once=True)


def _money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f} zł"


def _signed(value: float | None) -> str:
    return "—" if value is None else f"{value:+,.2f} zł"


def _kpi(
    key: str, title: str, value: str, icon: str, *, value_cls: str = "", hint: str = ""
) -> None:
    """One of the four figures above the chart.

    ``key`` names the figure on the card itself. Three of the four titles —
    "Predicted", "Change", "Confidence" — are words that also appear in the
    legend and in the table below, so a reader (or a test) looking for *the
    figure* needs something better than the text to find it by.
    """
    card = ui.card().classes(kpi_card_classes())
    card.props["data-kpi"] = key
    with card, ui.row().classes("items-center gap-4 w-full"):
        with ui.element("div").classes(
            f"h-10 w-10 rounded-xl {ACCENT_SOFT} flex items-center justify-center shrink-0"
        ):
            ui.icon(icon, size="1.6rem")
        with ui.column().classes("gap-1 min-w-0 flex-1"):
            ui.label(title).classes(SECTION_TITLE)
            ui.label(value).classes(f"{KPI_VALUE} {value_cls}")
            ui.label(hint or "—").classes(f"{MUTED} text-xs")
