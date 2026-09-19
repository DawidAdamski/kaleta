# SPDX-License-Identifier: AGPL-3.0-or-later
"""What-if scenarios — deltas laid over the forecast, with a verdict.

The page owns no arithmetic. It collects three kinds of delta, hands them to
``ScenarioService`` with the same baseline the Forecast page draws, and shows
what came back. Prophet is not required anywhere here: the baseline is
whatever forecaster is installed, and the deltas are applied on top of it.
"""

from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from nicegui import app, ui

from kaleta.exceptions import KaletaError, ValidationError
from kaleta.i18n import plural_key, t
from kaleta.schemas.planned_transaction import RecurrenceFrequency
from kaleta.schemas.scenario import FULL_INCOME_CUT, ScenarioDelta, ScenarioDeltaKind
from kaleta.services import with_session
from kaleta.services.forecast_service import ForecastResult, ForecastService
from kaleta.services.scenario_service import (
    DEFAULT_HORIZON_MONTHS,
    MAX_HORIZON_MONTHS,
    ScenarioService,
    ScenarioSimulation,
    horizon_days,
)
from kaleta.views.components.forecast_chart import forecast_chart
from kaleta.views.layout import page_layout
from kaleta.views.theme import (
    AMOUNT_EXPENSE,
    AMOUNT_INCOME,
    BODY_MUTED,
    DIALOG_TITLE,
    HAIRLINE_BOTTOM,
    KPI_VALUE_COMPACT,
    MONO,
    PAGE_TITLE,
    SECTION_CARD,
    SECTION_HEADING,
)

if TYPE_CHECKING:  # annotation-only: keeps views out of the models layer at runtime
    from kaleta.models.account import Account

_FORECAST_URL = "/forecast"
_SAFETY_FUNDS_URL = "/wizard/safety-funds"

#: How many deltas get a marker on the chart. One pin each (see
#: ``ScenarioSimulation.pins``); past half a dozen the chart is more label
#: than line, and the delta list below already names them all.
_MAX_PINS = 6

#: The horizons offered, in months. Presets rather than a typed number: the
#: control re-runs the forecast on every change, and typing "24" would run it
#: once for 2 months on the way. The widest is ``MAX_HORIZON_MONTHS``.
_HORIZONS: tuple[int, ...] = (3, 6, 12, 24)

#: The cadences a new bill realistically arrives on. Daily and weekly exist
#: in ``RecurrenceFrequency`` and the service handles them, but offering
#: them here invites a delta with 700 occurrences and no reader behind it.
_CADENCES: tuple[RecurrenceFrequency, ...] = (
    RecurrenceFrequency.MONTHLY,
    RecurrenceFrequency.QUARTERLY,
    RecurrenceFrequency.YEARLY,
)


def _fmt_amount(amount: Decimal | None) -> str:
    return "—" if amount is None else f"{amount:,.2f}"


def _fmt_months(months: Decimal | None) -> str:
    return "—" if months is None else f"{months:.1f}"


def _fmt_date(value: datetime.date | None) -> str:
    return "—" if value is None else value.isoformat()


def parse_amount(raw: object) -> Decimal:
    """Read a typed amount, accepting the comma a Polish keyboard produces."""
    text = str(raw or "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError(t("scenarios.bad_amount")) from exc
    if not value.is_finite():
        # ``Decimal`` parses "NaN" and "Infinity" happily. A NaN then makes
        # every later comparison raise ``InvalidOperation`` — an
        # ``ArithmeticError``, which the save handler does not catch, so the
        # dialog would fail with no toast at all; an infinity would reach
        # ``float()`` and the forecast arithmetic.
        raise ValidationError(t("scenarios.bad_amount"))
    return value


def parse_date(raw: object) -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(raw or ""))
    except ValueError as exc:
        raise ValidationError(t("scenarios.bad_date")) from exc


def delta_summary(delta: ScenarioDelta) -> str:
    """The one-line description under a delta's name in the list."""
    value = f"{delta.percent:+g}%" if delta.percent is not None else _fmt_amount(delta.amount)
    cadence = t(f"scenarios.cadence_{delta.cadence.value}") if delta.cadence is not None else ""
    return t(
        f"scenarios.summary_{delta.kind.value}",
        value=value,
        date=_fmt_date(delta.start_date),
        cadence=cadence.lower(),
    )


def notify_error(exc: KaletaError) -> None:
    """Show a handled error as a toast, from the handler's own task.

    ``views.error_handling.notify_kaleta_error`` is the house rule, and it
    is what this page would call — but under NiceGUI 3 it dispatches through
    ``asyncio.create_task``, and NiceGUI keys its slot stack by asyncio task
    id (``nicegui.slot.Slot.stacks``). The new task therefore has no slot,
    ``ui.context.client`` raises inside it, and the toast never reaches the
    browser: the failure is swallowed as "Task exception was never
    retrieved". Until that is fixed once for all eleven views that call it,
    this page notifies the way ``views/budget_plan/dialogs.py`` already
    does — synchronously, in the handler's own task.
    """
    ui.notify(exc.message, type="negative", multi_line=True)


def _verdict_figure(key: str, title: str, *, link: str | None = None) -> ui.column:
    """One labelled figure in the verdict strip, ready for its value.

    ``key`` goes on the column as ``data-verdict``. All three figures read
    "before → after", so their own text cannot say which of the three a
    reader — or a test — has landed on.
    """
    column = ui.column().classes("gap-0")
    column.props["data-verdict"] = key
    with column:
        if link is None:
            ui.label(title).classes(BODY_MUTED)
        else:
            with ui.row().classes("items-center gap-2"):
                ui.label(title).classes(BODY_MUTED)
                ui.link(t("scenarios.runway_link"), link).classes(f"{BODY_MUTED} text-xs")
    return column


def register() -> None:
    @ui.page("/wizard/scenarios")
    async def scenarios_page() -> None:
        # Session-only by design: the plan's open question settled on no
        # persistence in v1, so the delta list lives as long as the page.
        deltas: list[ScenarioDelta] = []
        state: dict[str, Any] = {
            "account": "all",
            "horizon": DEFAULT_HORIZON_MONTHS,
            "simulation": None,
        }

        async def _load_accounts(session: Any) -> list[Account]:
            return await ForecastService(session).available_accounts()

        accounts = await with_session(_load_accounts)
        account_options: dict[Any, str] = {"all": t("forecast.all_accounts")}
        account_options.update({a.id: a.name for a in accounts})

        async def _simulate(session: Any) -> ScenarioSimulation:
            account = state["account"]
            account_id = None if account == "all" else int(account)
            baseline: ForecastResult = await ForecastService(session).forecast_account(
                account_id,
                # The control asks in months, because a scenario is spoken in
                # months; the forecaster counts in days. The rule for turning
                # one into the other lives beside the horizon constants.
                horizon_days=horizon_days(int(state["horizon"])),
            )
            return await ScenarioService(session).simulate(baseline, deltas, account_id=account_id)

        async def refresh() -> None:
            try:
                state["simulation"] = await with_session(_simulate)
            except KaletaError as exc:
                notify_error(exc)
                return
            body.refresh()

        # ── Delta builder ────────────────────────────────────────────────
        async def open_delta_dialog(kind: ScenarioDeltaKind) -> None:
            with ui.dialog() as dialog, ui.card().classes("w-96 gap-2"):
                ui.label(t(f"scenarios.add_{kind.value}")).classes(DIALOG_TITLE)
                ui.label(t(f"scenarios.hint_{kind.value}")).classes(BODY_MUTED)
                label_in = ui.input(t("scenarios.label")).classes("w-full")
                mode_in = None
                if kind is ScenarioDeltaKind.INCOME_CHANGE:
                    mode_in = ui.toggle(
                        {
                            "percent": t("scenarios.as_percent"),
                            "amount": t("scenarios.as_amount"),
                        },
                        value="percent",
                    ).props("dense")
                amount_in = ui.input(t("scenarios.amount")).classes("w-full")
                cadence_in = None
                if kind is ScenarioDeltaKind.RECURRING:
                    cadence_in = ui.select(
                        {c: t(f"scenarios.cadence_{c.value}") for c in _CADENCES},
                        value=RecurrenceFrequency.MONTHLY,
                        label=t("scenarios.cadence"),
                    ).classes("w-full")
                date_in = ui.input(
                    t("scenarios.start_date"),
                    value=datetime.date.today().isoformat(),
                ).classes("w-full")

                async def save() -> None:
                    as_percent = mode_in is not None and mode_in.value == "percent"
                    try:
                        raw = parse_amount(amount_in.value)
                        if as_percent and raw < FULL_INCOME_CUT:
                            # The schema owns the limit; this owns the
                            # sentence. Schemas cannot translate, and this is
                            # the one shape rule a reader breaks by typing.
                            raise ValidationError(t("scenarios.bad_percent"))
                        delta = ScenarioDelta(
                            kind=kind,
                            label=(label_in.value or "").strip()
                            or t(f"scenarios.default_label_{kind.value}"),
                            start_date=parse_date(date_in.value),
                            amount=None if as_percent else raw,
                            percent=raw if as_percent else None,
                            cadence=cadence_in.value if cadence_in is not None else None,
                        )
                    except KaletaError as exc:
                        notify_error(exc)
                        return
                    except ValueError:
                        # The schema's remaining shape rules. The dialog makes
                        # them unreachable — the toggle and the cadence select
                        # see to that — so this is a backstop, and a reader
                        # gets a sentence rather than Pydantic's English trace.
                        notify_error(ValidationError(t("scenarios.bad_change")))
                        return
                    deltas.append(delta)
                    dialog.close()
                    await refresh()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button(t("common.cancel"), on_click=dialog.close).props("flat")
                    ui.button(t("common.save"), on_click=save).props("unelevated")
            # Built per click so its fields start empty; dropped on the way
            # out so a long session does not leave a stack of dead dialogs
            # in the DOM.
            dialog.on("hide", dialog.delete)
            dialog.open()

        async def remove_delta(index: int) -> None:
            del deltas[index]
            await refresh()

        async def clear_deltas() -> None:
            deltas.clear()
            await refresh()

        async def on_account(value: Any) -> None:
            state["account"] = value
            await refresh()

        async def on_horizon(value: int | None) -> None:
            # Clamped even though the options are: the cap belongs to the
            # forecaster, not to the widget that happens to feed it today.
            months = int(value or DEFAULT_HORIZON_MONTHS)
            state["horizon"] = max(1, min(months, MAX_HORIZON_MONTHS))
            await refresh()

        # ── Sections ─────────────────────────────────────────────────────
        def _deltas_card() -> None:
            with ui.card().classes(f"{SECTION_CARD} gap-2"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(t("scenarios.deltas_heading")).classes(SECTION_HEADING)
                    if deltas:
                        ui.button(t("scenarios.clear_all"), on_click=clear_deltas).props(
                            "flat dense"
                        )
                if not deltas:
                    ui.label(t("scenarios.no_deltas")).classes(BODY_MUTED)
                for index, delta in enumerate(deltas):
                    with ui.row().classes(f"w-full items-center gap-3 py-2 {HAIRLINE_BOTTOM}"):
                        with ui.column().classes("flex-1 min-w-0 gap-0"):
                            ui.label(delta.label).classes("text-sm font-medium truncate")
                            ui.label(delta_summary(delta)).classes(f"{BODY_MUTED} text-xs")
                        ui.button(
                            icon="close",
                            on_click=lambda _e, i=index: remove_delta(i),
                        ).props("flat dense round").classes("shrink-0")

        def _verdict_card(simulation: ScenarioSimulation) -> None:
            verdict = simulation.verdict
            with ui.card().classes(f"{SECTION_CARD} gap-3"):
                ui.label(t("scenarios.verdict_heading")).classes(SECTION_HEADING)
                with ui.row().classes("w-full gap-8 flex-wrap"):
                    with _verdict_figure("monthly_delta", t("scenarios.monthly_delta")):
                        tone = AMOUNT_INCOME if verdict.monthly_delta >= 0 else AMOUNT_EXPENSE
                        ui.label(_fmt_amount(verdict.monthly_delta)).classes(
                            f"{KPI_VALUE_COMPACT} {tone}"
                        )
                    with _verdict_figure("balance", t("scenarios.balance_at_horizon")):
                        ui.label(
                            t(
                                "scenarios.before_after",
                                before=_fmt_amount(verdict.balance_before),
                                after=_fmt_amount(verdict.balance_after),
                            )
                        ).classes(f"{MONO} text-base")
                    with _verdict_figure("runway", t("scenarios.runway"), link=_SAFETY_FUNDS_URL):
                        ui.label(
                            t(
                                "scenarios.before_after",
                                before=_fmt_months(verdict.runway_before),
                                after=_fmt_months(verdict.runway_after),
                            )
                        ).classes(f"{MONO} text-base")

                if verdict.goes_negative:
                    ui.label(
                        t(
                            "scenarios.goes_negative",
                            date=_fmt_date(verdict.first_negative_after),
                        )
                    ).classes(f"{AMOUNT_EXPENSE} text-sm")
                elif verdict.first_negative_after is not None:
                    ui.label(
                        t(
                            "scenarios.still_negative",
                            before=_fmt_date(verdict.first_negative_before),
                            after=_fmt_date(verdict.first_negative_after),
                        )
                    ).classes(f"{BODY_MUTED} text-sm")
                else:
                    ui.label(t("scenarios.stays_positive")).classes(f"{AMOUNT_INCOME} text-sm")

        def _chart_card(simulation: ScenarioSimulation) -> None:
            with ui.card().classes(f"{SECTION_CARD} gap-2"):
                # Named, because the page is one chart and three figures:
                # nothing else on it says which account they answer.
                ui.label(
                    t(
                        "scenarios.chart_heading",
                        account=simulation.baseline.account_name,
                    )
                ).classes(SECTION_HEADING)
                is_dark = bool(app.storage.user.get("dark_mode", False))
                ui.echart(
                    forecast_chart(
                        simulation.projected,
                        is_dark,
                        # Without deltas the two lines are identical, and a
                        # dotted twin under the prediction only reads as noise.
                        baseline=simulation.baseline if deltas else None,
                        scenarios=simulation.pins[:_MAX_PINS],
                    )
                ).classes("w-full h-96")
                ui.link(t("scenarios.forecast_link"), _FORECAST_URL).classes(
                    f"{BODY_MUTED} text-xs"
                )

        # ── Page ─────────────────────────────────────────────────────────
        with page_layout(t("scenarios.title"), wide=True):
            with ui.column().classes("gap-1"):
                ui.label(t("scenarios.title")).classes(PAGE_TITLE)
                ui.label(t("scenarios.subtitle")).classes(f"{BODY_MUTED} max-w-3xl")

            with ui.card().classes(f"{SECTION_CARD} gap-3"):
                with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                    ui.select(
                        account_options,
                        value=state["account"],
                        label=t("forecast.account"),
                        on_change=lambda e: on_account(e.value),
                    ).classes("w-56")
                    ui.select(
                        {m: t(plural_key("scenarios.horizon", m), months=m) for m in _HORIZONS},
                        value=state["horizon"],
                        label=t("scenarios.horizon_months"),
                        on_change=lambda e: on_horizon(e.value),
                    ).classes("w-40")
                with ui.row().classes("w-full items-center gap-2 flex-wrap"):
                    for kind in ScenarioDeltaKind:
                        ui.button(
                            t(f"scenarios.add_{kind.value}"),
                            icon="add",
                            on_click=lambda _e, k=kind: open_delta_dialog(k),
                        ).props("flat dense")

            @ui.refreshable
            def body() -> None:
                simulation: ScenarioSimulation | None = state["simulation"]
                _deltas_card()
                if simulation is None:
                    ui.label(t("scenarios.running")).classes(BODY_MUTED)
                    return
                if simulation.baseline.insufficient_data:
                    with ui.card().classes(SECTION_CARD):
                        ui.label(t("forecast.insufficient")).classes(BODY_MUTED)
                    return
                _verdict_card(simulation)
                _chart_card(simulation)

            body()

        await refresh()
