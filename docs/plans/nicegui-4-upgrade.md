---
plan_id: nicegui-4-upgrade
title: Upgrade NiceGUI 3.18 → 4.0
area: platform (dependencies, views)
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
---

# Upgrade NiceGUI 3.18 → 4.0

## Intent

NiceGUI 4.0.0 shipped on 2026-11-04. We are locked to 3.18.0 (`nicegui>=3.14.0`). 4.0 is a
cleanup release: it removes the APIs deprecated during 3.x, changes a few defaults, and
updates the bundled Quasar (2.18 → 2.35), AG Grid, plotly.js and three.js. Several of its
changes raise no error at all (release notes, "Behavior changes"). Without a deliberate pass,
a silent regression could reach the UI. Staying on 3.x also cuts us off from its fixes,
for example `app.remove_route()` with current FastAPI, and from its ~25% lower memory per
client.

## What the 2026-11-16 survey found

The survey was a grep against the 4.0 migration guide. The implementation pass re-checks
every line.

| 4.0 change | Hits in Kaleta | Impact |
|---|---|---|
| `httpx` is no longer installed by NiceGUI | `src/kaleta/services/bug_report_delivery.py` (base runtime), `src/kaleta/auth/providers/supabase.py` (`hosted` extra), 46 test files, 2 scripts | **Breaks the base install**: `httpx` is declared only in the `hosted` extra |
| Cleared text inputs hold `''`, not `None` (`ui.input`, `textarea`, `date_input`, `time_input`, `color_input`) | 118 such inputs in `src/kaleta/views` | Silent. Any `value is None` / `is not None` on these inputs changes meaning. The 9 hits found so far all sit on `ui.select`, which is unaffected, but each needs confirming |
| Element IDs in the DOM go from `c12` to `ng-12`; the `getElement` global stays, `id.slice(1)` no longer strips the prefix | `tests/e2e/test_reports_builder.py:392` (`getElement(el.id.slice(1))`) | The e2e test breaks |
| Quasar 2.35: dialogs close on mousedown on the backdrop, menus and tooltips stay attached while scrolling, `click` on `ui.item`/`ui.chip` implies `clickable`, the table pagination label uses an en dash | All dialogs, menus, tables | Possible e2e and visual drift |
| `ui.tab` outside `ui.tabs` raises `RuntimeError` | 15 `ui.tab(` call sites | Must each be nested |
| `ui.timer` callbacks must not swallow `CancelledError` | 21 timers; `suppress(asyncio.CancelledError)` in three schedulers' `stop()` (`event_retention_`, `subscription_settlement_`, `nbp_rate_scheduler.py`) | The scheduler hits await a task they cancelled themselves, so they are probably fine. Confirm none of this runs inside a `ui.timer` callback |
| `background_tasks.create(coroutine=…)` / awaitables passed to `app.on_startup(...)` removed | `mapping_section.py:237` passes positionally; `main.py` registers functions | Probably fine; confirm |
| Old snake/camel prop names ignored; `ui.add_scss`; `checkboxRenderer`; `sanitize=None`; `table.pagination` showing controls; `run.cpu_bound` spawn; `WEB_CONCURRENCY` > 1 | None found | Nothing to do, re-check during the pass |
| FastAPI ≥ 0.143.1, Python ≥ 3.11 | FastAPI 0.162.5, Python ≥ 3.13 | Already met |
| AG Grid, plotly, three.js, xterm, leaflet, joystick | Not used (we chart with `ui.echart`) | None |

## Scope

1. **Go through 3.19 first, as its own commit.** Lock `nicegui` 3.19.x, run the app and the
   full suite including e2e, and fix every NiceGUI deprecation warning. The warnings name the
   4.0 replacement. Commit separately, so a 4.0 regression can be bisected away from the
   deprecation fixes.
2. **Declare `httpx` explicitly.** Add it to `[project].dependencies`, because
   `bug_report_delivery` imports it in every install, and to the `dev` dependency group,
   because the tests use `httpx.AsyncClient`. Fix the `hosted` extra's comment ("NiceGUI
   already brings httpx in" is no longer true).
3. **Bump to 4.0.** Use `"nicegui>=4.0.0,<5"` in `pyproject.toml` and re-lock with
   `uv lock --upgrade-package nicegui`. Record in Implementation notes every other package
   whose version the lock moves (Starlette, uvicorn, websockets, …).
4. **Audit the text inputs.** Check every reader of a `ui.input` / `textarea` /
   `date_input` / `time_input` / `color_input` value, and every `bind_value` on one, for
   `None`-as-empty. Replace it with `not value` (which works on both versions), or use the
   `forward`/`backward` pair where a model must keep `None`. Record the audited call sites,
   grouped by file, in Implementation notes. Add a unit test for any helper that normalises
   an input value.
5. **Fix the e2e ID helper.** Change `test_reports_builder.py` to
   `getHtmlElement(el.id)` (or `parseHtmlId`). Check that no other test, CSS or JS relies on
   `c<N>` IDs.
6. **Behaviour pass.** Nest every `ui.tab` under its `ui.tabs`. Confirm the timer and
   scheduler `CancelledError` handling and the `background_tasks` / lifecycle registrations
   against the 4.0 rules. Fix any e2e drift from Quasar 2.35: backdrop mousedown, menu
   placement, the en dash in pagination labels. Fix the cause, never the assertion's strength.
7. **Docs.** Update `docs/tech-stack.md` where it names a NiceGUI version or behaviour.

## Not in scope

- Moving our own code from `httpx` to `httpx2`. We keep `httpx` declared, and a switch is a
  separate chore.
- Adopting 4.0 features: `pagination_controls` on tables, Python 3.15 support, plotly 7.
- A general dependency refresh. Only what NiceGUI 4.0's resolution forces moves, and each
  such move is listed in Implementation notes.
- Restyle or visual changes beyond restoring what 3.18 rendered.

## Acceptance criteria

- `uv run python -c "import importlib.metadata as m; v = m.version('nicegui'); assert v.startswith('4.'), v"`
- `uv run python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); assert any(x.startswith('httpx') for x in d['project']['dependencies']); assert any(x.startswith('httpx') for x in d['dependency-groups']['dev'])"`
- `test -z "$(grep -rn 'id.slice(1)' tests/e2e src/kaleta)"`
- `uv run mypy src/`
- `uv run lint-imports`
- `./scripts/verify.sh --e2e`
- `[manual]` Click through dashboard, transactions (add dialog, pagination), import (mapping
  step), budgets, reports builder, settings and the wizard in light and dark mode. Clear a
  text field, save, and check that the stored value is unchanged from 3.18 behaviour (empty
  text, not an error and not a literal `None`).

## Touchpoints

`pyproject.toml`, `uv.lock`, `src/kaleta/views/**` (input-value readers, `ui.tab` nesting),
`tests/e2e/test_reports_builder.py` and any e2e that drifts, `docs/tech-stack.md`. No model,
migration or i18n change is expected.

## Open questions (defaults apply in goal mode)

1. **`httpx` or `httpx2` for our own imports?** Default: keep `httpx`, declared explicitly.
   `httpx2` is out of scope (see above).
2. **Upper bound on the pin?** Default: `<5`, so a future major goes through a plan like this
   one.
3. **Is 3.19 a separate commit or folded in?** Default: a separate commit on the same branch
   (scope 1).
4. **No user-facing behaviour changes, so no new `KAL-*` scenario?** Default: none. If the
   input audit finds and fixes a real bug, that fix gets a scenario and a test, as Working
   Agreement §5 requires.

## Implementation notes

Decisions on the open questions, all taking the defaults: keep `httpx` declared explicitly
and leave `httpx2` alone; pin `nicegui>=4.0.0,<5`; make 3.19 a separate commit; add no
`KAL-*` scenario, because the audit found no user-facing bug to fix.

### 1. Through 3.19 (`build(deps): nicegui 3.18 -> 3.19`)

- NiceGUI reports deprecations with `helpers.warn_once` → `log.warning` on the `nicegui`
  logger, so they land in the e2e server log. A full e2e run on 3.19
  (`--basetemp` kept, `kaleta-e2e-server.log` grepped for
  `deprecat|NiceGUI 4|will be removed|should be a child`) showed **no warning**, and its 279
  tests passed.
- **The first full run failed: 97 failed, 4 errors.** This was not a NiceGUI regression.
  - `test_mfa.py::test_two_factor_authentication` waited more than 10 s for the
    recovery-codes dialog, because argon2 runs on the event loop (existing chore and plan
    `mfa-argon2-off-event-loop`). Enrolment had already committed, so every later test got
    401 from the API.
  - The test passes on its own, and the full rerun was all green.
  - This is logged as a chore (the test should disable 2FA in teardown). I did not fix it
    here, as it is out of scope.

### 2. `httpx` (`build(deps): declare httpx explicitly`)

- Added `httpx>=0.27` to `[project].dependencies` (for `bug_report_delivery`) and to the `dev`
  group (the API tests). The `hosted` extra keeps its own entry. Only its comment changed.

### 3. Bump (`build(deps): nicegui 3.19 -> 4.0`)

- `uv lock --upgrade-package nicegui`: **nicegui 3.19.0 → 4.0.0**, and added `httpx2 2.16.2`,
  `httpcore2 2.16.2`, `httpx2-jsfetch 1.0`, `truststore 0.10.5`. No other package moved.
  FastAPI 0.162.5, Starlette 1.7.0 and uvicorn 0.54.0 already met 4.0's minimums.
- `mypy src/` was clean on 4.0 (415 files). The typed `str` value of `ui.input` raised nothing.

### 4. Text-input audit (no code change needed)

I listed the readers of all 118 `ui.input`/`textarea`/`date_input`/`time_input`/
`color_input` calls with a script, then read the sites the script could not name by hand.
Every reader falls into one of these groups, and each stays correct with `''`:

- **`(x.value or "")` / `x.value or None` / `str(x.value or …)`:** most files, including
  `admin`, `credit`, `forecast`, `gifts`, `payees`, `tags`, `rules`, `payment_calendar`,
  `personal_loans/dialogs`, `subscriptions/dialogs`, `settings/*`, `layout` (search),
  `wizard_*`, `reports/page`, `reports/config_zone`, `import_view/settings_section` and
  `bug_report_dialog`.
- **Truthiness guards** (`if not x.value or not x.value.strip()`): `accounts`,
  `institutions`; `wizard_unplanned_radar` (the start date).
- **`x.value.strip()` with no `None` guard:** `categories`, `institutions` (color, website,
  description), `planned_transactions` (description). On 3.x a `None` here would have
  raised; with `''` it cannot.
- **Values that go into schemas which normalise blanks:** transaction `notes` (the `Notes`
  validator collapses blank to `None`) and split `note` (`r["note"] or ""`). The asset
  `description` is `NOT NULL DEFAULT ''`, and the edit dialog fills it from the stored string.
- **Dates:** `transactions/add_dialog` and `edit_dialog` (`if raw_date else today`),
  `safety_funds._parse_date` (`if not value`), `wizard_scenarios.parse_date`
  (`str(raw or "")`), `irregular_fund`, `wizard_salary`, `settings/data_tab` and
  `subscriptions/dialogs` (`fromisoformat` inside a `ValueError` handler; `''` is a
  `ValueError` as before).
- **`filter_bar` date and search inputs** read the raw Quasar `update:model-value` event args
  (`e.args`), not `.value`, and they already handle `None` and `''`.
- **Not a 4.0 regression:** the `reports_canned` date controls feed
  `fromisoformat(state["start"])` unguarded. An emptied field crashed on 3.x and still
  does. Logged as a chore.

All 9 `.value is None` / `is not None` hits in `src/kaleta/views` are on `ui.select`, which
4.0 leaves at `None`.

### 5. e2e ID helper

- `tests/e2e/test_reports_builder.py` now calls `getElement(el)` rather than the plan's
  suggested `getHtmlElement(el.id)`. `getHtmlElement` returns the DOM node, but the test
  needs the Vue component's `.chart`. In both 3.19 and 4.0, `getElement` accepts the element
  itself and strips the prefix (4.0 uses `parseHtmlId`). Nothing else in `src/` or `tests/`
  relies on `c<N>` IDs.

### 6. Behaviour pass

- **`ui.tab`:** all 15 call sites (`credit`, `settings/page`, `budgets/page`) sit inside
  `with ui.tabs()`.
- **`CancelledError`:** `suppress(asyncio.CancelledError)` only appears in the three
  schedulers' `stop()`, where it awaits a task the scheduler cancelled itself, outside any
  `ui.timer` callback. No timer callback catches it.
- **Lifecycle and background tasks:** `main.py` registers functions, not awaitables, with
  `on_startup`/`on_shutdown`. `background_tasks.create(result)` passes the awaitable
  positionally, not `coroutine=`.
- **None found:** `table.pagination` assignment or `hide-pagination`, `run.cpu_bound`/
  `io_bound`, `WEB_CONCURRENCY` (Containerfiles, compose files), `add_scss`,
  `sanitize=None`, old snake/camel prop names, AG Grid, plotly, scene, leaflet, xterm.
- **Quasar 2.35 drift:** the first `verify.sh --e2e` on 4.0 gave 277 passed and 2 failed, and
  both failures had the same cause, which the release notes do not mention. Quasar 2.35
  moves a `q-select`'s `aria-label` and the attributes passed through props (here
  `data-testid`) from the `.q-select` root onto its inner `q-select__focus-target` input.
  That input has no text, so `to_contain_text` read `''` even though the UI showed the right
  option (the input's `value` was "All Accounts" or "Car insurance").
  - Fix: `test_forecast._control` and the paid-for check in
    `test_irregular_fund.test_paying_an_item_from_the_fund` now select the `.q-select`
    that contains the labelled or test-id'd input, and assert the same text as before.
  - No view changed. A user sees the same control, and screen readers now get the label
    on the focusable element.
- **Test-DB disk full:** that first run was itself a rerun. The run before it failed in unit
  and integration with `No space left on device`, because the tmpfs Postgres container had
  been up for 27 hours. Restarting it with `scripts/test_db.sh down`/`up` fixed it. This is
  an environment problem, not part of the upgrade.

### 7. Docs

- `docs/tech-stack.md` and `AGENTS.md` both said "NiceGUI 2.x" and now say "4.x". `AGENTS.md`
  is outside the listed touchpoints, but it is the same stale fact in the stack summary, so
  I fixed it in the same docs commit rather than leaving the two files disagreeing.
