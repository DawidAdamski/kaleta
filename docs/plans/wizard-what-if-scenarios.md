---
plan_id: wizard-what-if-scenarios
title: Wizard — "what if" scenario simulator on top of the forecast engine
area: wizard
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#forecast
---

# Wizard — "what if" scenarios

## Intent

The wizard tile "Scenariusze «co jeśli»" (`step_scenarios`, budget
section) is Coming soon. Its description is the spec: *"Simulates the
impact of income drops, big purchases, or new recurring expenses on
your monthly balance and emergency fund runway."* This is the panel
that answers "can I afford X?" without spreadsheet gymnastics.

## Prior art (build on, don't duplicate)

- **Forecast engine** — `forecast_service` with naive + optional
  Prophet forecasters and model presets
  (KAL-FCT scenarios, `forecast-model-presets` archived plan). The
  simulator is *deltas applied to a baseline projection*, not a new
  forecasting engine.
- **Emergency runway** — `reserve_fund` model has `months_of_coverage`
  and the survival-months footer in `safety_funds.py`; runway impact
  reuses that maths.
- **Cross-panel projection layer** — ADR-030 (read-only projections
  across panels) is the architectural slot this fits into.
- **The forecast chart** — `restyle-forecast-on-load` (artboard 3a)
  rebuilt `views/forecast.py::_forecast_chart` on a linear time axis,
  with the confidence band, a `markLine` at today and a
  `markLine` + pin per scenario already in it, and moved the KPI figures
  behind `forecast_service.forecast_kpis` so they cannot disagree with
  the line. The "baseline chart (reuses forecast chart component)" below
  means *that* function: the before/after overlay is one more series on
  it, and the simulator's deltas are `ScenarioShift`s writ larger.
  Extract `_forecast_chart` into a shared component rather than copying
  it.

## Scope

- **Scenario model (in-memory v1, no DB)**: a scenario = baseline
  forecast + a list of typed deltas:
  - income change: ±% or ±amount from month M (e.g. "income −30%
    from October"),
  - one-off purchase: amount + date (e.g. "buy a car for 40k in
    March"),
  - new recurring expense/income: amount + cadence + start date.
- **Simulation service** (pure): apply deltas to the baseline monthly
  balance projection; outputs per-month balance series, first month
  below zero (if any), and emergency-fund runway (months of essential
  spending covered) before vs after.
- **Panel page** at `/wizard/scenarios` (route in `_STEP_ROUTES`):
  - baseline chart (reuses forecast chart component),
  - delta builder (add/remove the three delta types),
  - before/after overlay + verdict strip ("balance stays positive;
    runway drops 5.2 → 3.1 months"),
  - works with the naive forecaster — Prophet must NOT be required
    (respect the optional-extra principle).
- **Persistence (stretch, keep only if cheap)**: save named scenarios
  per user; otherwise explicitly session-only in v1 — decide in Open
  questions before starting.
- **Product doc**: add a "What-if scenarios" section to
  `docs/product/financial-wizard.md` (spec-first).
- **BDD**: new Feature (`KAL-WIF`) with `@planned` scenarios: income
  drop shifts projected balance; one-off purchase shows runway before/
  after; new recurring expense moves the first-negative-month marker;
  panel functional without Prophet installed. Retag as tests land.

Out of scope: Monte Carlo / probabilistic bands, AI-suggested
scenarios (paid tier), scenario → budget writeback ("apply this
scenario to my plan" is a future plan), gift planning (KAL-GFT).

## Acceptance criteria

- `uv run pytest tests/unit/services -q`
- `grep -q "KAL-WIF-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Without Prophet installed: build "income −30% + car 40k
  in March" on seed data; overlay renders, runway verdict updates,
  removing deltas restores the baseline exactly.

## Touchpoints

- `src/kaleta/services/` new `scenario_service.py` (+ types in
  `schemas/`)
- `src/kaleta/services/forecast_service.py` (baseline access — read
  only), `reserve_fund_service` (runway maths — read only)
- `src/kaleta/views/wizard.py` (`_STEP_ROUTES`), new view module,
  `views/chart_utils.py`
- `docs/product/financial-wizard.md`, `docs/bdd.md` (KAL-WIF)
- `tests/unit/services/`, `tests/e2e/`

## Open questions

1. Persist scenarios in v1? Default: **no** — session-only; a
   `saved_scenarios` table is a follow-up plan once the UX proves out.
2. Runway definition: essential-spending average from history (as the
   emergency-fund wizard computes it) or total average spending?
   Default: **same formula the Safety Funds panel already uses** —
   one definition across the app.
3. Horizon: default 12 months, max 24? Default: **yes** (matches
   forecast presets).

## Implementation notes

### Open questions, resolved

1. **Persistence: no.** Session-only in v1, as the default said. The
   delta list is a local in the page function; leaving the page clears
   it (`KAL-WIF-006`, `@manual`). A `saved_scenarios` table stays a
   follow-up plan.
2. **Runway: the Safety Funds formula, borrowed not copied.**
   `ReserveFundService._trailing_monthly_expense` became public
   `trailing_monthly_expense` so the simulator measures against the
   same burn the panel shows, and `emergency_progress()` was factored
   out of `emergency_cover_months()` so the simulator can take the fund
   *balances* rather than recover one from a ratio already rounded to a
   tenth of a month (review finding: that loses up to 0.05 × burn, and a
   small purchase would then shift the answer by the wrong amount).

   The rule, documented on `ScenarioService._runway_after`: **a scenario
   can only shorten the runway.** The figure asks "if income stopped,
   how long would the fund last", so nothing added to income lengthens
   it — not a raise, not a new recurring income stream, not a windfall.
   The first draft had only income *changes* excluded, which let a
   positive recurring delta lower the burn and stretch the runway while
   an income change of the same size left it alone: two answers to one
   question (review finding, now covered by four tests in `TestRunway`).
   Spending still shortens it: a purchase draws the fund down, a new
   bill raises the burn.

   `runway_after` is `None` exactly when `runway_before` is — no
   emergency fund, or nothing spent to measure against. That guard sits
   in `simulate`, because `_runway_after` would see a zero balance and
   answer "0.0 months", which is a figure where there is none.
3. **Horizon: 12 months default, 24 max.** `DEFAULT_HORIZON_MONTHS` /
   `MAX_HORIZON_MONTHS`; the control asks in months and converts at 30
   days each, because the forecaster counts in days and a scenario is
   spoken in months.

### Decisions a reviewer should know

- **The chart is the Forecast page's, not a lookalike.**
  `views/forecast.py::_forecast_chart` moved verbatim to
  `views/components/forecast_chart.py` as public `forecast_chart`;
  `forecast.py` keeps `_forecast_chart = forecast_chart` so its call
  sites and `tests/unit/views/test_forecast_chart.py` are untouched.
  The before/after overlay is that function's existing `baseline=`
  series, and the delta pins are its existing `scenarios=` markers.
- **Deltas compile to dated cash events, not to a slope.** A new
  monthly bill is thirty-odd separate withdrawals handed to
  `forecast_service.apply_scenarios` — the same function the Forecast
  page's own what-if pins already use. The line therefore steps where
  the money leaves.
- **`compile_deltas` clamps every start date to the forecast's first
  point.** `apply_scenarios` keys its deltas by *exact* date, and the
  forecast begins the day after the last transaction — so on an account
  used today it begins tomorrow. Without the clamp the panel's own
  default date ("today") would silently move nothing, on exactly the
  accounts people use. This is the same rule `default_scenario_date`
  already applies on the Forecast page.
- **A percentage income change is read against the selected account's
  income**, over the same 90-day window the runway uses
  (`ScenarioService.trailing_monthly_income(account_id=...)`). The
  balance series records what is left over, never what came in, so a
  percentage has no meaning without it; and reading it against the
  household total would apply a cut the account never took.
- **Only monthly / quarterly / yearly cadences are offered.** The
  service handles the whole `RecurrenceFrequency` enum, but daily and
  weekly in this dialog invite a delta with 700 occurrences and no
  reader behind it. `_MAX_OCCURRENCES = 1000` guards the service side.
- **The verdict figures carry `data-verdict`**, the way the Forecast
  KPIs carry `data-kpi`: all three read "before → after", so their own
  text cannot say which one a reader — or a test — has landed on. The
  chart card names its account for the same reason.
- **Prophet is not required anywhere.** The e2e instance runs the dev
  dependencies, which exclude the optional extra, so `KAL-WIF-004`
  passing *is* the scenario rather than a claim about it.

### Found on the way: `notify_kaleta_error` never reaches the browser

Building the panel's "income cannot fall by more than 100%" guard turned up
a defect in a shared helper, **not introduced here**:

`views/error_handling.notify_kaleta_error` dispatches through
`asyncio.create_task`, and NiceGUI keys its slot stack by asyncio *task id*
(`nicegui.slot.Slot.stacks`). The new task therefore starts with an empty
stack, `ui.context.client` raises inside it, and the toast never reaches the
browser — the failure is swallowed as "Task exception was never retrieved".
`getattr(ui.context, "client", None)` does not help: the default only
covers a missing attribute, not an exception raised inside the property.

Eleven view modules call it, so this is a cross-cutting fix that wants its
own issue and branch (one issue = one branch = one PR), not a drive-by in a
feature plan. This page therefore notifies from the handler's own task — a
local `notify_error`, carrying the reason — the way
`views/budget_plan/dialogs.py` already does. Swap it back to the house rule
once the helper is fixed.

**Not yet filed.** Opening the issue is the maintainer's call, not this
branch's — flagged in the PR description so the workaround does not quietly
become permanent.

### Review findings addressed

- **Removed assertions in `tests/unit/views/test_wizard_index.py`** (gate
  warning, rule 4). `test_a_step_with_no_page_behind_it_says_so` asserted the
  index still had an unrouted half to read its rule off. `scenarios` was the
  last routine without a page, so that half is now empty and the premise is
  gone. The rule itself — `is_open` is exactly "has a route" — is asserted on
  a `WizardStep` built by hand, so it keeps holding for the next routine
  added to `_STEPS` before its page exists, and a new
  `test_every_routine_now_has_a_page` records the new fact. Nothing was
  loosened: the file went from 5 assertions to 7, and the surviving
  `all(... if not s.is_open)` — which now iterates an empty list and can never
  fail — was replaced by a positive `is_open` case on a hand-built step.
- **`_runway_after` no longer takes `monthly_income`** — it was dead state,
  and its own docstring explained why it was ignored.
- **The months→days horizon rule moved to `scenario_service.horizon_days`**,
  beside `DEFAULT_HORIZON_MONTHS` / `MAX_HORIZON_MONTHS`, rather than sitting
  in the view as `_DAYS_PER_MONTH`.
- **`TRAILING_WINDOW_MONTHS`** is now a shared constant in
  `reserve_fund_service`, so the burn and the income compared against it
  cannot drift onto different numbers of months.
- **One chart pin per delta**, not the first six events. A recurring delta
  compiles to a dozen dated withdrawals and used up the whole budget, leaving
  a later car purchase unmarked. The first fix deduped by label, which
  collapsed two deltas that both took the dialog's default name; pins are now
  built per delta by `compile_delta`, so they are right by construction
  (`ScenarioSimulation.pins`).
- **−100% is allowed.** The guard read `<= -100`, so the panel refused
  "I lose all my income" — the exact case the emergency-fund runway exists
  for. `FULL_INCOME_CUT` in `schemas/scenario.py` is now the single limit:
  the schema enforces it, the view supplies the translated sentence (schemas
  cannot translate). Boundary tests cover −100 accepted and −100.01 refused.
- **A cadence counts from its start date, not from the previous firing.** A
  bill on the 31st clamped to the 28th in February and then stayed on the
  28th for the rest of the series. `_occurrence(start, cadence, n)` puts it
  back on the 31st in March, where its owner will be looking for it.
- **The runway only counts deltas the horizon sees.** A purchase dated two
  years out emits no events, so the line never steps — and it must not draw
  the fund down either, or the figure and the chart beside it would describe
  different scenarios. `simulate` passes `_runway_after` only the deltas that
  compiled to something.
- **Both runway figures divide once.** The panel's `emergency_cover` sums each
  fund's months *after* rounding each to a tenth, so two funds at 1.04 months
  read 2.0 there while one division of the total reads 2.1 — and with no
  deltas at all the verdict showed a change. Both ends of the pair now go
  through `ScenarioService._runway`, which makes them comparable; the Safety
  Funds headline stays that panel's to define. Covered by a two-fund
  no-deltas invariant test.
- **`monthly_amount` resolves percent → amount in one place.** Written twice,
  the chart and the "Monthly cashflow" figure would eventually disagree.
- **The schema rejects a field the kind cannot use** — `percent` on a one-off
  or recurring delta, `cadence` on either of the others. Ignoring it silently
  would apply half a delta and say nothing about the rest.
- **The amount field carries the sign convention** ("Amount (negative takes
  money out)"), so typing `50000` for a car is not silently a windfall. A
  full expense/income toggle would widen the builder past the plan.

### Beyond the plan's touchpoints

`reserve_fund_service` is listed as "runway maths — read only". Three changes
landed in it anyway, all so the simulator could borrow the definition instead
of copying it: `_trailing_monthly_expense` became public, `emergency_progress`
was factored out of `emergency_cover_months` (same result, balances exposed),
and `TRAILING_WINDOW_MONTHS` replaced a bare `/ 3`. No behaviour changed —
`emergency_cover_months` returns exactly what it did — and the existing
reserve-fund unit and e2e tests pass unchanged. Flagged for the reviewer
rather than buried.

### Known and left alone

A percentage income change on an account with no income in the trailing 90
days resolves to zero and quietly does nothing — it appears in the change
list and moves no figure. Warning about it needs the income figure in the
dialog, before the simulation runs, which is more machinery than the case
deserves in v1. Worth a look if anyone hits it.

### Not done, on purpose

- Monte Carlo bands, AI-suggested scenarios and scenario → budget
  writeback are the plan's Out of scope and stayed out.
- `views/chart_utils.py` is listed as a touchpoint but needed no
  change: the extracted chart already uses it.
