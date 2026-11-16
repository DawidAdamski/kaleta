---
plan_id: nicegui-4-upgrade
title: Upgrade NiceGUI 3.18 → 4.0
area: platform (dependencies, views)
effort: medium
status: draft
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

_Filled in during implementation._
