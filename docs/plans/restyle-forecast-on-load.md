---
plan_id: restyle-forecast-on-load
title: Restyle — Forecast runs baseline on load, controls on the title row, one linear-axis chart (artboard 3a)
area: forecast
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#forecast
---

# Restyle — Forecast runs on load, one chart, four KPIs

## Intent

`views/forecast.py` opens empty behind a Run button. Artboard `3a` runs
the baseline on load and demotes Run to a re-run; the account / horizon
/ preset controls move onto the title row so the first thing you see is
a forecast. Four KPIs: balance today, predicted at horizon, change,
confidence. One ECharts instance: solid ink actuals, dashed accent
prediction, `#EFCDB2` confidence band, dotted muted baseline when a
non-baseline preset is active, a dashed `markLine` at today, and a
`markLine` + point per scenario. The Prophet-unavailable banner shrinks
to a footnote under the chart title.

Two things the prototype got wrong first and the plan must get right:
the x-axis must be **linear across history and forecast** (a category
axis over sparse dates compresses history), and the KPI figures must
include the scenario shifts if the chart's line does.

Depends on `restyle-theme-tokens` (chart palette).

## Scope

- **Run on load**: on page open, run the baseline forecast for the
  saved account / horizon / preset (`app.storage.user` keys
  `forecast_preset`, `forecast_scenarios` keep working; add
  `forecast_account`, `forecast_horizon`). Show a skeleton while it
  runs; Run becomes "Re-run" and is only needed after changing controls
  (or auto-run on change — see open question).
- **Title row**: page title left; account select, horizon select,
  preset toggle right, compact (no floating labels). Prophet footnote
  under the chart title with the docs link, replaces the amber banner.
- **KPIs**: today's balance, predicted at horizon, change (signed,
  `k-amount`), confidence at horizon (interval width as ±). Computed
  from the same series the chart draws, scenario shifts included.
- **Chart** (`_forecast_chart`): `xAxis.type = "time"`; series: actuals
  (ink, solid), prediction (accent, dashed), confidence band (two
  stacked series with `areaStyle` `#EFCDB2`, dark: accent at 0.18
  opacity), baseline (muted, dotted) only when preset ≠ baseline,
  `markLine` at today (dashed border colour), one `markLine` + point per
  scenario. Axis styling through `chart_utils.apply_dark`.
- Scenario chips: keep add / remove and persistence; restyle as
  `k-filter-chip`s.
- BDD: extend Account Balance Forecast — `KAL-FCT-010` "forecast page
  shows a baseline without pressing Run" (@automated, e2e) and
  `KAL-FCT-011` "KPIs include scenario shifts" (@automated, unit on the
  KPI helper).

Out of scope: forecaster models / presets (`forecast-model-presets`,
archived); scenario semantics; What-if scenarios plan
(`wizard-what-if-scenarios`, draft — that plan should build on this
chart, note it there).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_forecast_service.py -q`
- `uv run pytest tests/e2e/test_forecast.py -q`
- `grep -q '"time"' src/kaleta/views/forecast.py`
- `grep -q "KAL-FCT-010" docs/bdd.md`
- `grep -q "KAL-FCT-011" docs/bdd.md`
- `test "$(grep -c 'bg-amber-1' src/kaleta/views/forecast.py)" = 0`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Open /forecast on seed data: a chart is visible within a
  few seconds with no click; history is not compressed relative to the
  forecast segment; add a scenario: a marker appears and the predicted
  KPI moves by the scenario amount. Compare to artboard `3a` in light
  and dark, with and without Prophet installed.

## Touchpoints

- `src/kaleta/views/forecast.py` (page, `_forecast_chart`, `_kpi`)
- `src/kaleta/views/chart_utils.py`
- `src/kaleta/services/forecast_service.py` (KPI helper if it lives in
  the service; no model change)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (`forecast.rerun`,
  `forecast.kpi_confidence`, footnote key)
- `docs/bdd.md`, `tests/e2e/test_forecast.py`, `tests/unit/`

## Open questions

1. Auto-run on every control change or explicit Re-run? Default:
   **auto-run on change with a 300 ms debounce**; Re-run stays for the
   Prophet case where a run is slow (>2 s) — then changes only mark the
   chart stale and Re-run applies them.
2. Confidence KPI format? Default: **`± X zł`** (half the interval width
   at horizon), tooltip explains.

## Implementation notes

### Read this before reviewing the diff

Sixth in a stack — theme-tokens → dashboard → transactions-filter-chips →
budgets-pace-bars → budget-plan-grid → import-mapping → this one. None
merged. This plan's own diff is:

    git diff plan/restyle-import-mapping...HEAD

and its PR is opened with `--base plan/restyle-import-mapping`. Against
`main` it would carry six other plans' work and break the one-issue,
one-branch, one-PR rule.

### Open questions, resolved

1. **Auto-run on control change, or an explicit Re-run?** Plan default, taken
   as written: auto-run with a 300 ms debounce when the naive projection is
   in use, and, when Prophet is installed and a run costs seconds, a change
   only marks the chart stale — `stale_hint` under the title, the Re-run
   button raised out of `flat` — and Re-run applies it. `is_prophet_available()`
   is the proxy for "a run is slow", which is the plan's own wording.
2. **Confidence KPI format?** Plan default: `± X zł`, half the 80 % interval
   at the horizon, with the hint line under the figure saying so.

### The band was drawn above the line it was meant to surround

Not a restyle: a bug the restyle uncovered. The band is drawn by stacking its
height on an invisible floor series, and the floor was the **upper** bound —
so the shading ran from `upper` to `2·upper − lower`, sitting entirely above
the prediction. `KAL-FCT-001` has said "a shaded confidence interval
surrounds the prediction" all along. The floor is the lower bound now, and
`tests/unit/views/test_forecast_chart.py` asserts floor + height = upper.

### The x-axis is time, and the two lines meet

A `category` axis spaces points evenly whatever dates they carry, so ninety
daily history points beside sixty daily forecast points came out compressed —
the past appeared to happen faster than the future. Every series now carries
`[date, value]` pairs on an `xAxis.type = "time"`. The prediction is prepended
with the last historical point so the solid and dashed lines meet at today
instead of leaving a day-wide gap.

### The horizon is the horizon

`predicted_balance_30d` answers about day 30 whatever horizon was asked for.
`forecast_kpis` reads the **last** forecast point, so a 90-day request gets a
90-day answer, and the figure carries the date under it. The service property
is left alone — it has other callers.

### The figures cannot disagree with the picture

`forecast_kpis(result)` takes the same `ForecastResult` the chart is drawn
from — after `apply_preset` and `apply_scenarios` — so a what-if that lifts
the line lifts the figures by exactly as much, and the interval that moved
with it leaves the ± unchanged. Recomputing them from the raw forecast was
the prototype's mistake.

### A scenario never costs a forecast

The first version sent a scenario change down the same path as a control
change — stale-and-Re-run under Prophet — which meant adding a windfall and
watching nothing move, the opposite of what `KAL-FCT-011` promises. Both
`apply_preset` and `apply_scenarios` are pure post-processing on a result the
forecaster has already produced, so the page keeps that result and redraws
from it: a scenario or a preset is instant whichever forecaster is installed,
and only the account and the horizon are worth a new run. That widens open
question 1 slightly — the preset is a title-row control but never marks the
chart stale — and it is the better answer for the same reason the plan gives.

### One run at a time, and the later request is served, not dropped

Second review round. The first single-flight guard returned early while a run
was in flight, which swapped "last to finish wins" for "the later request
vanishes": changing the account during the on-load run left the select and
storage showing the new account and the chart showing the old one. `run_forecast`
loops — a request that arrives mid-run sets `pending`, and the loop serves it
before it exits — so the chart ends up answering the controls as they stand.

The stale mark had the mirror-image bug under Prophet: a run that started
*before* the change would clear it on landing, leaving the old account's
forecast under the new selection with nothing to say so. `_sync_stale()`
compares what the run was asked against what is selected now, and runs after
every redraw, so the mark survives exactly as long as it is true. The naive
path is exempt: its re-run follows within the debounce, so there is nothing
to warn about.

`_RunState` is a dataclass rather than a `dict[str, Any]` — it holds a
`ForecastResult`, and mypy strict should be able to say so.

### One run at a time, and a failure that does not strand the page

The on-load timer, the debounce and the Re-run button can all ask for a run
at once, and two in flight end with the last to *finish* on screen rather
than the last one asked for — the race the debounce exists to prevent. A
flag in `_run_state` refuses a second start. The run also catches its own
failure now: the skeleton is the whole page once the page draws on load, and
a `try/finally` with no `except` would have left it standing there for good.
`forecast.failed` is the new key.

### One timer, and a dialog that outlives its own Save

Two NiceGUI traps, both found by the e2e:

- A `ui.timer` created inside an event handler belongs to the handler's
  ambient slot. Save redraws the scenario chips — including the chip whose
  click opened the dialog — so by the time the timer was constructed its
  parent was gone (`The parent element this slot belongs to has been
  deleted`). There is one debounce timer now, built with the page and armed
  by `activate()`.
- The add-scenario dialog had the same problem: built inside the chip row, it
  was deleted halfway through its own handler. It is built once with the page
  and reset on open.

### `data-kpi` on each figure

Three of the four KPI titles — Predicted, Change, Confidence — are words that
also appear in the chart legend and in the upcoming-14 table, so neither a
reader's eye nor a test can find *the figure* by its text. Each card names
itself.

### e2e: the page remembers the account

`forecast_account` and `forecast_horizon` are new persisted keys, which the
plan asks for. The e2e suite shares one browser session, so "All Accounts is
the default" stopped being true once another test picked an account:
`KAL-FCT-003` selects it explicitly, which is what the scenario says anyway.
The scenario test removes its own scenario at the end for the same reason —
and that exercises removal.

### KAL-FCT-011 is an e2e, not a unit test

Scope says "@automated, unit on the KPI helper", but `scripts/spec_coverage.py`
only scans `tests/e2e` and `tests/integration`, so a `Covers:` in
`tests/unit` counts for nothing. The rule is unit-tested either way
(`TestForecastKpis`); the scenario is carried by an e2e that adds a windfall
through the dialog and asserts the predicted and change figures move by its
amount, then takes it away again.

### Scenarios reworded, not re-scoped

`KAL-FCT-001`, `002`, `003` and `007` each had a "When I click Run forecast"
step that the page no longer has; they now describe a page that has already
run. `KAL-FCT-009` describes a footnote rather than the amber banner. The
banner's keys (`fallback_banner`, `click_run`, `run`, `running`,
`current_balance`, `predicted_30`, `change_30`) are gone from both locales
rather than left behind as cruft.

### New tokens

`--k-accent-soft` (`#F4E3D5` / `#3A2E24`) behind the KPI icons, replacing the
per-view `bg-blue-500/10 text-blue-600` triplets, and `.k-skeleton` so the
wait looks like this app rather than Quasar's grey. Both in `theme.py` with
the rest.

### The stale mark goes away again

Fourth review round. The mark was one-way: `_sync_stale()` un-raised the
button but left "Controls changed — press Re-run" on the status line, so
changing the account and changing it back left a hint contradicting the chart
under it — the behaviour the third round's notes claimed. The settled status
line is kept on `_RunState` and put back when the controls match.

`_sync_stale()` also ran after a *failed* run and, finding no result to match
against, replaced "The forecast could not be run" with "press Re-run" —
blaming the user for a failure. With no usable run there is nothing for the
controls to be ahead of, and the line already says something truer, so it
leaves both alone.

The Re-run button keeps `color=primary` in both states and toggles only
`flat`, so it does not change colour the first time a run lands. And if a run
raises, a request that arrived while it was in flight is re-armed on the way
out rather than dropped with the loop.

### What "never costs a forecast" actually means

Third review round. The claim had two holes. With a run in flight, a scenario
change redrew the *previous* run over the skeleton and replaced the
"Running…" line — and pointlessly, since the run reads the scenarios when it
draws. With no usable run behind us, the same change started a full forecast,
Prophet included; but a scenario does not turn insufficient history into
sufficient history. `_redraw_now` does nothing in both cases, and the chips
update either way.

A failed run used to leave the previous account's result in `run_state.raw`,
so the next scenario or preset drew the old account's chart under the new
selection — the very mismatch the previous round set out to fix. The failure
path clears it.

`_on_controls_changed` asks `_sync_stale()` rather than asserting
`_mark_stale()`: changing the account and changing it straight back leaves
the chart answering the controls again, and the hint has to go with it.

The two band series are `tooltip: {show: false}`. The band's own value is its
*height*, so hovering listed "200" in a column of zł figures as though it
were a balance.

### Errors are domain errors

The first version caught bare `Exception` and wrote a muted "Try again" into
the status line, which turns a programming error into a footnote — against
AGENTS.md, which says views catch `KaletaError` and call
`notify_kaleta_error`. They do now. Anything else still clears the skeleton
first, because the skeleton is the whole page once the page draws on load,
and is then re-raised as the bug it is.

### A scenario dated today does nothing, and the dialog stops offering it

Rounds three to five, one finding chasing its own tail, and worth writing
down properly.

`markPoint` originally drew only where a scenario's date matched a forecast
point exactly, so a scenario saved with the dialog's default — today — got a
line and no pin. The obvious fix was to snap the pin to the next point. That
was wrong, and worse than the symptom: `apply_scenarios` keys its deltas by
**exact** date (`deltas.get(p.date)`), so a scenario dated today shifts
nothing at all. A snapped pin would have marked a bend in a line that never
bent, and `KAL-FCT-011` — "the predicted figure moves by that amount" —
would have been false for the commonest scenario there is.

Scenario semantics are out of scope here, so the rule stays and the view
stops walking into it: `point_shifted_by` mirrors the exact-date rule from
`forecast_service`, where it can be read next to the function it mirrors, and
a date that moves nothing still gets its `markLine`, because the user put it
there, but no pin claims otherwise.

The first attempt at the dialog default — "tomorrow" — was wrong for the same
reason as the snap, and caught by the sixth review round. The forecast does
not start tomorrow: `NaiveForecaster` runs from the day after the last
**transaction**, so an account with something posted today is forecast from
tomorrow and one quiet for a month was forecast from weeks ago. Which dates
shift anything is a property of the data, not the calendar.
`default_scenario_date(result)` therefore reads the answer off the run in
hand — the first forecast point from today onward, or the first point at all
when the whole forecast is behind us. The e2e tests say in a comment that
they depend on `seed_many_transactions` posting one transaction today, which
is what makes "today + 7" and "today + 90" the right dates to assert.

The exact-date rule is brittle for a feature meant to answer "what if I buy a
car in March": `wizard-what-if-scenarios` should widen it to on-or-after when
it builds on this chart, which is a decision for that plan and not this one.
Chore-inbox candidate either way.

### KAL-FCT-003 says what the app does

The scenario claimed "individual account lines are shown as secondary
series". No such series exists, here or in the plan's list of them, and the
test never checked for it — an `@automated` tag over a clause nothing
verifies. It now says the four figures describe the combined balance, which
is what the page shows and what the test asserts.

### One rule for the stale mark, tested without Prophet

The mark has been wrong in three different ways — it would not go away, it
outlived a failure and blamed the user for it, and it erased "Insufficient
transaction history" with "press Re-run". All three are the same shape: a
branch that read one condition and missed another, on a path this environment
cannot run, because Prophet is not installed.

`stale_action(prophet_available, drawn, running, controls_match)` is that
branch as one rule, in a pure function with a unit test per case. The page
says nothing about staleness on the naive path (its re-run lands within the
debounce), while a run is in flight (the recorded account is still the
previous one), or when nothing was drawn (a failure or too little history —
the line already says something truer, and it is not the user's doing).

### Smaller things from round five

`_sync_stale()` does nothing while a run is in flight: the state it compares
against still describes the *previous* run, so changing the controls back to
that run's values mid-flight replaced "Running Prophet…" with a status line
describing a chart that was not on screen.

The KPI hint line falls back to a non-breaking space rather than an em dash —
"—" is what `_money` prints for a missing figure, so under a figure that has
one it read as "no data".

The scenario chips carry `role="button"` and `tabindex="0"` and answer Enter
and Space, like the filter chips from artboard 2a.

### Smaller things from round six

`_page_is_live()` guards the failure paths too, not only the success one: a
run that fails after the reader has navigated away would otherwise clear and
write into a deleted page, and raise a toast at nobody.

The scenario chip's figure goes through `format_net_amount` — the ledger's
own convention, two decimals, and no sign on zero. It printed `+0 zł` for a
zero scenario, and rounded a 0.40 zł one to `+0 zł` while the KPI beside it
moved.

`KAL-FCT-003` says the chart is titled for all accounts and the four figures
stand above it, which is what the test checks. The previous wording — "its
four figures describe that combined balance" — claimed an arithmetic
relationship nothing verified, the same fault as the "secondary series"
clause it replaced.

### Round seven, and one thing left for the manual pass

`stale_action` returns a `Literal`, so a typo in one of its three answers is
a type error rather than a silent no-op — worth it for the rule the notes
above call wrong three times.

The Change figure goes through `format_net_amount` like the scenario chip
beside it, so a zero change reads `0.00 zł` rather than `+0.00 zł`
(KAL-TXN-017: zero has no direction).

`KAL-FCT-002` said the chart "extends 90 days beyond today". It extends 90
days past the last balance it knows, which is only today on an account with
something posted today — the e2e's seed does, which is why it passed.
Reworded rather than fixed: moving the forecast's origin is scenario
semantics, and out of scope.

**Left for the owner's Prophet pass:** with Prophet installed and the
controls changed but Re-run not yet pressed, the add-scenario dialog reads
its default date off the *previous* account's forecast, so it can offer a
date that shifts nothing once Re-run lands. Narrow, and only on the stale
path; the fix belongs with whatever settles how a stale page behaves.

### Round eight: the exemption has an end

`stale_action` left the mark alone whenever nothing was drawn, which is right
while the controls have not moved — a failure or too little history is not
the reader's doing, and "press Re-run" would blame them for it. But it is
wrong the moment the selection changes: account A's "Insufficient
transaction history" is not an answer about account B. The exemption now
applies only when the controls still match, and the match is measured
against what the last run was *asked* (recorded before the await) rather than
what it returned, so a failed run is still something the controls can be
compared with.

Three scenarios came out of this round rather than one. `KAL-FCT-011` now
carries literal figures — 1000.00 opening, 800.00 at the horizon, +5000.00
scenario, 5800.00 and 4800.00 after — because Working Agreement §11 wants
verification tests to assert literals from the scenario, and the old test
computed its expectations by calling `forecast_kpis` twice. `KAL-FCT-012` is
`@manual`: the Prophet stale/Re-run behaviour is user-facing and cannot be
automated where Prophet is not installed, so §5 wants it written down for the
owner's pass rather than left in these notes. `KAL-FCT-013` says a what-if
never waits for a run, and the e2e asserts it by the absence of a skeleton
and of the "Running…" line.

The horizon hint prints `13.12.2026` rather than `2026-12-13`, the format the
rest of the app writes dates in. The figures themselves still use the
app-wide `,` thousands separator, which reads oddly in Polish — the same
Chore-inbox candidate the import-mapping plan recorded, not something to fix
one page at a time.

### A run outlives the page it was started for

`test_every_nav_entry_routes` clicks every sidebar entry in turn, and failed
once in four full suite runs after this page started running on load. The
mechanism is real even if the flake was not reproduced: the on-load timer
fires ~50 ms after connect, the click on the next entry can land while the
run is still out at the forecaster, and `_render_skeleton` then builds
elements inside a `kpi_row` that no longer exists — "the parent element this
slot belongs to has been deleted", raised out of a background task, for a
result nobody can see. `_page_is_live()` checks `client.is_deleted` before
each draw. Three full suite runs since, all green.

### The e2e server binds a fixed port

Not a finding about this plan, but it cost an hour: `tests/e2e/conftest.py`
starts its server on 8081 and waits for *a* server to answer there. Two
concurrent e2e sessions therefore do not fail loudly — the second one talks
to the first one's server, whose database holds a different API token, and
the suite returns 73 failures that all read `401 Unauthorized`. Worth a
Chore inbox line: bind an ephemeral port, or fail when 8081 is already
taken.

### Not done

The `[manual]` criterion — `/forecast` on seed data compared to artboard `3a`
in light and dark, with and without Prophet — is the owner's visual pass.
This repo's dev environment has no Prophet, so the stale-then-Re-run branch
of open question 1 is exercised by reading, not by running: it is part of
that manual pass. Forecaster models, presets and scenario semantics are
untouched, as Scope says.
