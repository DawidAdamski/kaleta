# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import datetime
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from nicegui import app, ui

from kaleta.exceptions import KaletaError
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
    default_scenario_date,
    forecast_kpis,
)
from kaleta.services.forecasters import is_prophet_available
from kaleta.views.components.amount_label import (
    format_net_amount,
    format_signed_amount,
    net_tone,
)
from kaleta.views.components.forecast_chart import forecast_chart
from kaleta.views.error_handling import notify_kaleta_error
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

#: How long a control change waits before it re-runs itself.
_DEBOUNCE_SECONDS = 0.3

#: Dates the reader sees, in the format the rest of the app writes them.
_DATE_FMT = "%d.%m.%Y"


@dataclass
class _RunState:
    """What the last run produced, and what is being asked of the next one.

    ``raw`` is the forecaster's own answer, before any preset or scenario:
    both are pure post-processing, so the page redraws from this rather than
    asking again. ``account`` and ``horizon`` record what it was asked, so
    the page can tell whether the controls have moved on since.
    """

    raw: ForecastResult | None = None
    account: int | str = "all"
    horizon: int = 60
    running: bool = False
    #: A request that arrived mid-run, to be served before the loop exits.
    pending: bool = False
    #: What the status line says when the chart answers the controls — kept
    #: so that clearing a stale mark can put it back.
    status: str = ""


#: Where the Prophet footnote points.
_PROPHET_DOCS_URL = "https://github.com/DawidAdamski/kaleta#optional-forecasting"

_HORIZONS = (30, 60, 90)


def stale_action(
    *, prophet_available: bool, running: bool, controls_match: bool
) -> Literal["leave", "clear", "mark"]:
    """Whether the "press Re-run" mark should be set, cleared, or left alone.

    A rule rather than a branch, because it has been wrong four times: a mark
    that would not go away, one that outlived a failure and blamed the reader
    for it, one that erased "Insufficient transaction history", and one that
    stuck after the selection went away and came back.

    What is on screen answers the controls, or it does not — and what is on
    screen may perfectly well be a failure or a warning, as long as it is
    *this* selection's failure or warning. The page says nothing about
    staleness in only two cases: the naive path, whose re-run lands within
    the debounce, and a run in flight, whose recorded selection is still the
    previous one.
    """
    if not prophet_available or running:
        return "leave"
    return "clear" if controls_match else "mark"


def _saved_horizon() -> int:
    raw = app.storage.user.get("forecast_horizon", 60)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 60
    return value if value in _HORIZONS else 60


def _saved_account(options: dict[int | str, str]) -> int | str:
    """The remembered account, if it is still one of the offered ones.

    Storage round-trips through JSON, so an id saved as ``7`` can come back
    as ``"7"``; both spellings are tried before giving up on it.
    """
    raw = app.storage.user.get("forecast_account", "all")
    if isinstance(raw, int | str) and raw in options:
        return raw
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

            run_state = _RunState()
            client = ui.context.client

            def _page_is_live() -> bool:
                """Is anyone still looking at this page?

                The page starts a run on its own now, and a run outlives a
                click on the next nav entry. Drawing into a torn-down page
                raises out of a background task ("the parent element this
                slot belongs to has been deleted") for a result nobody can
                see.
                """
                return not client.is_deleted

            def _mark_stale() -> None:
                """Prophet runs are slow, so a change asks before spending one."""
                status.set_text(t("forecast.stale_hint"))
                run_btn.props(remove="flat")

            def _controls_match_last_run() -> bool:
                """Is what is on screen an answer to what is selected now?

                Measured against what the last run was *asked*, not what it
                returned: a run that failed for account A still answers the
                question "is A what you have selected?".
                """
                return run_state.account == account_sel.value and run_state.horizon == int(
                    horizon_sel.value
                )

            def _sync_stale() -> None:
                """Say whether what is on screen still answers what is selected.

                A run that started before the user changed the account is
                still a run of the *old* account, and when it lands it must
                not quietly clear the mark that says so — nor, when the user
                changes it straight back, keep a mark that is no longer true.

                Two exemptions, and only two: the naive path, whose re-run
                follows within the debounce, and a run in flight, whose
                recorded selection is still the previous one. A failure or a
                warning is this selection's answer like any other — see
                :func:`stale_action`, which owns the rule.
                """
                action = stale_action(
                    prophet_available=prophet_available,
                    running=run_state.running,
                    controls_match=_controls_match_last_run(),
                )
                if action == "clear":
                    run_btn.props(add="flat")
                    status.set_text(run_state.status)
                elif action == "mark":
                    _mark_stale()

            def _on_controls_changed() -> None:
                """The account or the horizon changed — that needs a new run."""
                app.storage.user["forecast_account"] = account_sel.value
                app.storage.user["forecast_horizon"] = horizon_sel.value
                if prophet_available:
                    # Asked, not asserted: changing the account and changing
                    # it straight back leaves the chart answering the controls
                    # again, and the mark has to go with it.
                    _sync_stale()
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
                _redraw_now()

            # A place for the delay timers to live. A `ui.timer` belongs to
            # whatever slot is current when it is built, and a handler's
            # ambient slot can be gone by the time it runs — Save redraws the
            # chip that opened the dialog. This element is built with the page
            # and outlives all of them.
            timer_host = ui.element("div").style("display:none")
            _debounce = {"token": 0}

            def _debounced_run() -> None:
                """Coalesce a flurry of control changes into one run.

                Without it, arrowing through a select's options starts a
                forecast per keystroke, and the last one to *finish* — not the
                last one asked for — wins.

                A one-shot timer per change, not one repeating timer armed by
                a flag: `ui.timer(..., active=False)` still ticks on its own
                schedule and `activate()` only flips a flag, so a change would
                fire anywhere from 0 to 300 ms later and a second change would
                not push the first one back. Each change starts its own delay
                and the newest token is the only one that fires.
                """
                _debounce["token"] += 1
                token = _debounce["token"]

                async def _fire() -> None:
                    if _debounce["token"] == token and _page_is_live():
                        await run_forecast()

                with timer_host:
                    ui.timer(_DEBOUNCE_SECONDS, _fire, once=True)

            def _render_scenarios() -> None:
                scenario_row.clear()
                with scenario_row:
                    if not scenarios:
                        ui.label(t("forecast.scenarios_empty")).classes(f"{MUTED} text-xs")
                    for idx, s in enumerate(scenarios):
                        amt = float(s.get("amount", 0))
                        label = str(s.get("label", "—"))
                        with ui.row().classes(f"{FILTER_CHIP} gap-2"):
                            ui.label(f"{label} · {_display_date(s.get('date'))}").classes("text-xs")
                            ui.label(f"{format_net_amount(amt)} zł").classes(
                                f"{MONO} text-xs {net_tone(Decimal(str(amt)))}"
                            )
                            remove = (
                                ui.icon("close", size="14px")
                                .classes("cursor-pointer")
                                .props('tabindex="0" role="button"')
                            )
                            remove.props["aria-label"] = t("forecast.scenario_remove", label=label)

                            def _remove(_: Any = None, i: int = idx) -> None:
                                scenarios.pop(i)
                                app.storage.user["forecast_scenarios"] = scenarios
                                _render_scenarios()
                                _on_scenarios_changed()

                            remove.on("click", _remove)
                            remove.on("keydown.enter", _remove)
                            remove.on("keydown.space.prevent", _remove)

                    add = ui.row().classes(f"{FILTER_CHIP} {FILTER_CHIP_EMPTY} gap-1")
                    add.props('tabindex="0" role="button"')
                    with add:
                        ui.icon("add", size="14px")
                        ui.label(t("forecast.scenario_add")).classes("text-xs")
                    for event in ("click", "keydown.enter", "keydown.space.prevent"):
                        add.on(event, _open_add_scenario_dialog)

            def _on_scenarios_changed() -> None:
                """A scenario never costs a forecast.

                ``apply_scenarios`` shifts the series that has already been
                computed, so the figures and the chart can be redrawn from the
                run in hand. Sending this down the stale/Re-run path would
                have meant adding a windfall and watching nothing move, which
                is the opposite of what KAL-FCT-011 promises.
                """
                _redraw_now()

            def _redraw_now() -> None:
                """Redraw for something that costs no forecast, if it can.

                Two cases where it cannot, and neither is worth a run: while
                one is in flight, the run reads the scenarios and the preset
                as it draws, so it will already show them — redrawing here
                would paint the previous account over the skeleton and take
                the "Running…" line with it. And with no usable run behind us
                there is nothing to shift: a scenario does not turn
                insufficient history into sufficient history.
                """
                if run_state.running:
                    return
                _redraw_from_last_run()

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
                # A date the forecast actually has a point on, read off the
                # run in hand: only those shift anything, and which ones they
                # are depends on when the account last saw a transaction, not
                # on the calendar. Offering a date that does nothing is a trap.
                usable = default_scenario_date(run_state.raw)
                date_input.value = (usable or datetime.date.today()).isoformat()
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

                One run at a time — the on-load timer, the debounce and the
                Re-run button can all ask at once, and two in flight end with
                the last to *finish* on screen rather than the last one asked
                for. A request that arrives mid-run is not dropped, though:
                it is served by the next turn of the loop, so the chart ends
                up answering the controls as they now stand.
                """
                if run_state.running:
                    run_state.pending = True
                    return
                run_state.running = True
                try:
                    while True:
                        run_state.pending = False
                        await _run_once()
                        if not run_state.pending:
                            break
                finally:
                    run_state.running = False
                    # Nothing below touches anything the page still owns if
                    # the reader has gone; a `return` here would swallow the
                    # exception that brought us out of the loop.
                    if _page_is_live():
                        run_btn.props(remove="loading")
                        if run_state.pending:
                            # The loop did not exit on its own terms — a run
                            # raised. The request that arrived meanwhile is
                            # still owed an answer.
                            _debounced_run()
                        _sync_stale()

            async def _run_once() -> None:
                if not _page_is_live():
                    return
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
                # Recorded before the run, not after: whatever it returns —
                # a result, nothing, or an error — the page now shows an
                # answer to *these* controls.
                run_state.account = chosen
                run_state.horizon = horizon

                async def _ask(session: Any) -> ForecastResult:
                    result: ForecastResult = await ForecastService(session).forecast_account(
                        account_id=acct_id, horizon_days=horizon
                    )
                    return result

                try:
                    raw = await with_session(_ask)
                except KaletaError as exc:
                    # The previous account's result goes with it: keeping it
                    # would let the next scenario or preset redraw the old
                    # account's chart under the new selection.
                    run_state.raw = None
                    if _page_is_live():
                        _clear_and_say(t("forecast.failed"))
                        notify_kaleta_error(exc)
                    return
                except Exception:
                    # Not a domain error and not ours to explain away: clear
                    # the skeleton, which is the whole page now that the page
                    # draws on load, then let the bug reach the logs as one.
                    run_state.raw = None
                    if _page_is_live():
                        _clear_and_say(t("forecast.failed"))
                    raise

                run_state.raw = raw
                if not _redraw_from_last_run() and _page_is_live():
                    _clear_and_say(t("forecast.insufficient"))

            def _clear_and_say(message: str) -> None:
                """Nothing to show, and the reason why.

                The reason is remembered like any other settled line: clearing
                a stale mark has to put back what this selection actually
                said, which may well be "Insufficient transaction history".
                """
                run_state.status = message
                chart_container.clear()
                kpi_row.clear()
                status.set_text(message)

            def _redraw_from_last_run() -> bool:
                """Redraw from the run in hand, with the preset and scenarios on.

                Both are pure post-processing — ``apply_preset`` blends toward
                a band the forecaster already gave us, ``apply_scenarios``
                adds a constant from a date onward — so neither is worth a
                second trip to Prophet. Returns False when there is nothing to
                draw, which is the caller's cue to say why.
                """
                raw = run_state.raw
                if raw is None or raw.insufficient_data or not raw.points:
                    return False
                if not _page_is_live():
                    # Nothing to draw into, and the caller's "False" would be
                    # read as "no data"; say the draw happened and stop.
                    return True

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

                run_state.status = t(
                    "forecast.status_running",
                    account=result.account_name,
                    days=len(result.historical),
                    horizon=run_state.horizon,
                )
                status.set_text(run_state.status)
                _render_kpis(forecast_kpis(result))
                _render_chart(result, baseline, shifts)
                # The status line has just been rewritten; if the controls
                # have moved on since this run, say so again.
                _sync_stale()
                return True

            def _render_kpis(kpis: ForecastKpis) -> None:
                kpi_row.clear()
                with kpi_row:
                    _kpi(
                        "balance_today",
                        t("forecast.kpi_balance_today"),
                        _money(kpis.balance_today),
                        "account_balance",
                        # Dated like the predicted figure beside it: history
                        # ends at the last transaction, so on a quiet account
                        # "today" is not today.
                        hint=_at_date(kpis.balance_date),
                    )
                    _kpi(
                        "predicted",
                        t("forecast.kpi_predicted"),
                        _money(kpis.predicted),
                        "trending_flat",
                        hint=_at_date(kpis.horizon_date),
                    )
                    change_tone = (
                        net_tone(Decimal(str(kpis.change))) if kpis.change is not None else MUTED
                    )
                    _kpi(
                        "change",
                        t("forecast.kpi_change"),
                        _money_net(kpis.change),
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
                            forecast_chart(result, is_dark, baseline=baseline, scenarios=shifts)
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
                            "date": p.date.strftime(_DATE_FMT),
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
                            "date": occ.date.strftime(_DATE_FMT),
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

            async def _on_rerun_clicked() -> None:
                """Re-run, unless the run it would ask for is already out.

                Pressing it again while the same selection is in flight would
                queue a second identical run through `pending` — with Prophet,
                one impatient click costs another several seconds.
                """
                if run_state.running and _controls_match_last_run():
                    return
                await run_forecast()

            run_btn.on("click", _on_rerun_clicked)

            # The page answers before it is asked: a forecast is what this
            # page is for, and an empty frame behind a button was a question
            # the user had already answered by navigating here.
            _render_skeleton()
            with timer_host:
                ui.timer(0.05, run_forecast, once=True)


def _at_date(day: datetime.date | None) -> str:
    """ "on 13.12.2026" — the date a figure belongs to, or nothing."""
    return "" if day is None else t("forecast.kpi_at_date", date=day.strftime(_DATE_FMT))


def _display_date(iso: object) -> str:
    """A stored ISO date as the reader's format, or as-is if it is not one."""
    try:
        return datetime.date.fromisoformat(str(iso)).strftime(_DATE_FMT)
    except (TypeError, ValueError):
        return str(iso or "")


def _money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f} zł"


def _money_net(value: float | None) -> str:
    """A signed figure, through the ledger's own rule — zero carries no sign."""
    return "—" if value is None else f"{format_net_amount(value)} zł"


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
            # A blank line, not an em dash: "—" is what `_money` prints for a
            # missing figure, and under a figure that has one it would read as
            # "no data" rather than "nothing more to say".
            ui.label(hint or "\u00a0").classes(f"{MUTED} text-xs")
