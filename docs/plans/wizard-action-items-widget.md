---
plan_id: wizard-action-items-widget
title: Dashboard — Wizard action-items widget
area: wizard
effort: small
roadmap_ref: ../product/financial-wizard.md#shared-wizard-patterns
status: in-progress
deferred_to: q4-2026
---

# Dashboard — Wizard action-items widget

## Intent

The wizard deep-dive says *"every section produces action items
… show up on the dashboard if the user pins the Wizard widget."*
Nothing like that exists yet. Each wizard section surfaces its
suggestions only on its own page. A user who opens the dashboard
first never sees "3 subscriptions to review this month" or "2
loans are due this week" without navigating into each section.

Ship a single dashboard widget that aggregates the open
suggestions / action items from every wizard section and renders
them as a compact list.

## Scope

- **New widget** `wizard_actions` registered in
  `dashboard_widgets.py`:
  - `default_size = (2, 2)`
  - `allowed_sizes = ((2, 2), (4, 2))`
- **Aggregator service** `WizardActionService` with a single
  method `get_action_items() -> list[ActionItem]` that queries
  every wizard area for open items:
  - **Subscriptions** — untracked candidates + subscriptions
    flagged for review (`review_at <= today`).
  - **Safety Funds** — funds behind schedule (contribution
    target vs current progress).
  - **Personal Loans** — loans `due_soon` or `overdue` (uses
    the same thresholds as the reminders system).
  - **Monthly Readiness** — "plan next month" flag when there
    are < N days to month-end.
  - **Budget Builder** — "annual revision due" if the last
    build is > 11 months old (stretch goal; defer if the data
    doesn't exist).
  - **Getting Started** — any pending mentor hints.
- **`ActionItem`** schema: `kind`, `title`, `body` (short),
  `severity` (`info` | `warning` | `danger`), `href` (link to
  the source page with a query anchor if possible), `count`
  (optional — for "X subscriptions need review"), `created_at`.
- **Widget render** — grouped by section with a section header
  and a compact list; each item is a clickable row that routes
  to `href`. A small severity dot on the left. If there are no
  action items, show a friendly empty state ("All clear —
  nothing needs attention").
- **Link to full wizard** — bottom of the widget has a "Open
  financial wizard" button that routes to `/wizard`.
- **i18n** — title, subtitle, empty state, per-kind action
  messages.
- **Tests** — unit tests for the aggregator per section with a
  seeded DB.

Out of scope:
- Dismissing an action item from the widget — rely on the
  source page to resolve (e.g. confirming a subscription).
- AI-generated narrative / monthly summary (paid tier).
- Custom user-defined action items.
- Pagination; cap at ~12 items total with a "+N more" tail.

## Acceptance criteria

- With no pending items, the widget renders the empty state.
- With a subscription flagged for review, the widget lists it
  with a link to `/wizard/subscriptions?focus=<id>` (or
  equivalent).
- With a personal loan due in 3 days, the widget shows a
  `warning`-severity row; same loan overdue → `danger`.
- Sorting: `danger` → `warning` → `info`; inside a severity
  bucket, newer first.
- Widget resizes (`(2, 2)` ↔ `(4, 2)`) and both sizes render
  correctly.
- Aggregator returns results in < 200 ms on a seeded DB of
  ~1000 transactions.

Executable (the DoD gate and `plan-archiver` run these):

- `test -f src/kaleta/services/wizard_action_service.py`
- `grep -q "wizard_actions" src/kaleta/views/dashboard_widgets/registry.py`
- `uv run pytest tests/unit/services/test_wizard_action_service.py -q`
- `uv run pytest tests/unit/views/test_wizard_actions_widget.py -q`
- `uv run pytest tests/e2e/test_wizard_actions_widget.py -q`
- `grep -q '"wizard_actions_empty"' src/kaleta/i18n/locales/en.json`
- `grep -q '"wizard_actions_empty"' src/kaleta/i18n/locales/pl.json`
- `grep -qE "KAL-WAC-002 @automated" docs/bdd.md`
- `grep -qE "KAL-WAC-003 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

Manual (owner, before archiving):

- `[manual]` With no wizard section reporting anything, the widget shows the
  empty state (KAL-WAC-001).
- `[manual]` The widget renders correctly at both 2x2 and 4x2 (KAL-WAC-005).

## Touchpoints

- New file `src/kaleta/services/wizard_action_service.py`.
- New schema types in `src/kaleta/schemas/wizard_actions.py`
  (or inline in the service module).
- `src/kaleta/views/dashboard_widgets.py` — register the new
  widget function.
- `src/kaleta/views/dashboard.py` — `DEFAULT_WIDGETS` gains
  `wizard_actions` at a sensible position (near the top, after
  KPIs and before charts).
- `src/kaleta/i18n/locales/{en,pl}.json` — widget labels.
- `tests/unit/services/test_wizard_action_service.py`.

## Open questions

1. **Include in default layout?** Risk: new users see a
   full widget before they've used the wizard. Default:
   **yes, include** — empty state is helpful. New users also
   get mentor hints from Getting Started.
2. **Re-fetch cadence** — once per page load, or via
   websocket refresh every N minutes? Default: **per page
   load** — cheap enough.
3. **Inline dismiss** — add a dismiss-for-7-days action per
   row? Default: **no for v1** — rely on the source page.
4. **Severity mapping** — how do we pick? Default: domain-
   aware per kind (overdue loan = danger; review reminder =
   info).

## Implementation notes

### Open questions — resolved

1. **Include in default layout?** Default taken: **yes**. `wizard_actions`
   sits in `DEFAULT_WIDGETS` right after `savings_rate_kpi` and before
   `cashflow_chart` — the plan's "after KPIs, before charts".
2. **Re-fetch cadence.** Default taken: **per page load**. The widget calls
   `WizardActionService.get_action_items()` once inside the dashboard's
   existing session; no polling, no websocket refresh.
3. **Inline dismiss.** Default taken: **no for v1**. Rows link to the source
   page. The one exception is mentor hints, which the *wizard page* already
   lets you dismiss — see "Mentor dismissals" below.
4. **Severity mapping.** Default taken: **domain-aware per kind**. Overdue
   loan → `danger`; loan due within `LOAN_DUE_SOON_DAYS` (7) and an
   under-target safety fund → `warning`; subscription reviews, detector
   candidates, the month-end nudge and mentor hints → `info`. A loan due
   *today* is deliberately a `warning`, not a `danger` — the day has not run
   out yet; `danger` starts the morning after (`due < today`).

### Where the plan's data model did not match the code

The plan was written against an older shape of the repo. Three gaps, and
what was done about each:

- **`Subscription.review_at` does not exist.** The model has
  `next_expected_at`. "Flagged for review" is therefore read as *a renewal
  whose expected charge date has passed* — the charge should have landed and
  wants confirming. Filtered to `status == ACTIVE`, the same filter
  `upcoming_renewals` uses, so muted and cancelled subscriptions never nag
  (regression-tested both ways).
- **Reserve funds have no contribution schedule.** "Behind schedule" is read
  off the only progress signal the model carries: `progress_pct < 1` on a
  non-archived fund with a target above zero.
- **There is no reminders system** to borrow loan thresholds from
  (`wizard-reminders` is still a draft plan). `LOAN_DUE_SOON_DAYS = 7` and
  `PLAN_NEXT_MONTH_WITHIN_DAYS = 5` are declared as class constants so they
  are reviewable in one place and can be pointed at the reminders system when
  it lands.
- **Budget Builder ("annual revision due")** was the plan's own stretch goal,
  to be deferred if the data does not exist. There is no "last build" stamp
  on the yearly-plan model, so it is deferred as the plan allows.

### Decisions a reviewer should know

- **Items carry i18n keys, not strings.** No service in this repo imports
  `kaleta.i18n`, and `MentorSuggestion` already establishes `title_key` /
  `body_key` / `params`. `ActionItem` follows that, so the plan's `title` /
  `body` fields are named `title_key` / `body_key` and the widget translates.
- **`dashboard_widgets.py` is now a package.** The plan's touchpoints name a
  single module; the code has since split into `views/dashboard_widgets/`
  with `registry.py` holding `DEFAULT_WIDGETS`. New widget module:
  `views/dashboard_widgets/wizard_actions.py`, imported from the package
  `__init__` so the `@register` decorator runs.
- **Mentor dismissals stay a view concern.** `views/wizard.py` stores them in
  `app.storage.user["wizard_mentor_dismissed"]`, which services cannot read
  (import-linter forbids `services -> nicegui`). The service therefore emits
  every hint with a `dismiss_key`, and the widget filters against the same
  storage key before capping the list. `drop_dismissed(items, dismissed)` takes
  the key set as an argument rather than reading storage itself, which keeps it
  pure and unit-testable (`tests/unit/views/test_wizard_actions_widget.py`);
  `_dismissed_mentor_keys()` is the thin storage read at the call site.
- **`?focus=<id>` is currently inert.** The acceptance criterion names
  `/wizard/subscriptions?focus=<id>` explicitly, and the link does land on the
  right page, but none of the three wizard pages read a `focus` query param
  today. Wiring highlight/scroll into `views/subscriptions/`,
  `views/personal_loans/` and `views/safety_funds.py` is outside this plan's
  touchpoints, so the param is left as a forward-compatible hook — worth a
  Chore-inbox line.
- **`count` lives on the item, not in `params`.** The renderer merges it into
  the interpolation values (`_message_params`), so the plan's `count` field is
  the single source for "X subscriptions need review" rather than being
  duplicated into `params` by each collector.
- **A loan due today gets its own message.** `loan_due_soon_body` would render
  "Due in 0 days"; `days == 0` uses `loan_due_today_body` instead.
- **Cap, not pagination.** Out-of-scope bullet reads "Pagination; cap at ~12
  items total with a '+N more' tail" — implemented as `MAX_ROWS = 12` plus a
  `+N more` label. Grouping is by section, but the *ranked* order decides
  which section leads, so the most urgent item always brings its group to the
  top rather than a fixed section order burying an overdue loan.
- **Perf.** `detect_candidates` is the only expensive collector.
  `test_aggregates_under_200ms_on_a_thousand_transactions` pins the plan's
  budget with a real 1 000-row insert.

### Fallout: `tests/e2e/test_dashboard_customize.py` had to be hardened

Adding an 18th widget to `DEFAULT_WIDGETS` made the dashboard's initial
render measurably longer, which turned two latent races in the
dashboard-customize e2e test (merged to `main` as PR #72) into a real flake —
it failed in one DoD-gate run at 84 s wall-clock while passing every local
run at 69–75 s. Both races are in the test, not in production code, and both
scale with the number of widgets:

1. **The layout POST is fire-and-forget.** `__kaletaPostDashLayout()` issues a
   bare `fetch()`. Navigating with `page.goto()` before it lands aborts it, so
   the resize is never persisted and the assertion *after* the reload sees the
   old size. `_cycle_size` now wraps the call in `page.expect_response(
   "**/_dashboard/layout")` and asserts the response is OK.
2. **A POST fired mid-render persists a truncated layout.**
   `__kaletaPostDashLayout()` serialises whatever `#dash-grid` contains at
   that instant, and NiceGUI streams widgets in one at a time — so resizing
   before the grid is complete can save a layout missing every widget yet to
   arrive (`net_worth_trend` is last in `DEFAULT_WIDGETS`, so it is the first
   casualty). New `_wait_for_grid_settled()` blocks until the grid's child
   count holds steady across three 200 ms polls.

Honest limitation: the flake could **not** be reproduced locally, including a
full e2e suite run under 8 concurrent busy-loops (86 passed, 74 s). The fix
therefore rests on the mechanism above rather than on a red-to-green
demonstration. Both changes replace timing luck with an explicit wait for the
event that actually matters, so they are correct regardless of which of the
two fired in the gate's run.

### BDD

New `## Feature: Wizard Action Items`, KAL-WAC-001..005. 002/003/004 are
`@automated` via `tests/e2e/test_wizard_actions_widget.py`. 001 (empty state)
and 005 (both widget sizes) are `@manual`: the e2e suite shares one database
across the whole session, so "no wizard section has an open item" cannot be
guaranteed at the point this test runs, and asserting it would make the suite
order-dependent.
