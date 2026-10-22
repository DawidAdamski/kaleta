---
plan_id: budget-builder-apply-handler-stack
title: Budget Builder — register the Apply-confirm handler once
area: wizard
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Budget Builder — register the Apply-confirm handler once

## Intent
In the Budget Builder's Apply flow the diff dialog's Confirm handler was
registered inside `_on_apply`, which runs every time the user opens the diff.
NiceGUI appends click listeners, so after opening the diff N times a single
Confirm applied the plan N times. Register the handler exactly once, like the
annual-review dialog does, so confirming applies the plan once.

## Scope
- `src/kaleta/views/budget_builder.py`: move `_confirm` out of `_on_apply`;
  wire `diff_apply_btn.on_click(_confirm)` once at dialog-build time; carry the
  payload the diff was computed from in a mutable holder that `_on_apply` sets.
- Add BDD scenario KAL-BBD-001 and an e2e that guards apply-once.
- Add an e2e seed helper to populate a yearly plan.
- **Not in scope**: the `YearlyPlanService.apply`/`bulk_upsert` idempotency and
  the duplicate-key race it exposes under concurrent applies (noted below); the
  rest of the Budget Builder UI; the annual-review dialog.

## Acceptance criteria
- `uv run pytest tests/e2e/test_budget_builder_apply.py -q` (needs a live DB; run under verify.sh --e2e)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/views/budget_builder.py`
- `tests/e2e/test_budget_builder_apply.py` (new)
- `tests/e2e/seed_helpers.py` (`seed_yearly_plan_variable`)
- `docs/bdd.md` (Feature: Budget Builder, KAL-BBD-001)

## Open questions
- None blocking. See the idempotency note below for a follow-up candidate.

## Implementation notes

### Ground truth — NiceGUI 3.18 handler stacking (measured, not assumed)
Installed NiceGUI is **3.18.0**. `Button.on_click` calls `Element.on('click', …)`,
which stores each listener under a fresh `uuid4` key in
`self._event_listeners` (a dict) — so repeat calls **accumulate**, they do not
replace. On the client (`nicegui.js`), every listener in `element.events` is
pushed onto `props.onClick`, and a new listener id forces a re-render
("Event listeners changed after initial definition. Re-rendering affected
elements."). A single DOM click then fires **all** bound handlers.

Measured in the real Budget Builder page (Playwright, pre-fix), opening the diff
twice then clicking Confirm once:
- the confirm button emits **2** `event` messages (two distinct `listener_id`s)
  from the one click;
- the server runs `_confirm` **twice** (proven with a temporary per-call file
  log: two lines ~0.8 ms apart);
- `YearlyPlanService.apply` therefore runs twice.

So the double-apply **does reproduce** in this version. The prior
investigation's "only one apply / one toast" is explained, not contradicted:
the duplication is partly *masked* for a human because `apply` is an idempotent
upsert (identical rows) **and** Quasar groups the two identical "applied" toasts
into a single visible notification (no count badge persisted). When no prior
budget rows exist, though, the two concurrent applies race on the first INSERT
and raise `UniqueViolationError` on `uq_budget_category_period` — a real,
user-facing failure, observed in the pre-fix e2e server log.

### Why the test asserts emit count, not toast count
Because the toasts group and the upsert is idempotent, "one toast" and "one
January row" are both true pre-fix as well — they do not distinguish the bug.
The honest, deterministic discriminator is the number of apply round-trips the
Confirm click makes: **2 pre-fix, 1 post-fix**. The e2e hooks `window.socket`
to count `event` emits on the single Confirm click and asserts exactly one
(BDD literal: "applied exactly once"). Verified: fails pre-fix ("saw 2"),
passes post-fix.

### Follow-up (out of scope, candidate for chores)
`YearlyPlanService.apply` → `BudgetService.bulk_upsert` is not safe under two
concurrent applies of a brand-new plan: both see no existing rows and INSERT,
tripping the unique constraint. The handler fix removes the trigger, but the
service is not itself concurrency-idempotent. Left out of this slice by scope.
