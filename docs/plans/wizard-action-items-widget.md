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
  storage key before capping the list.
- **`?focus=<id>` is currently inert.** The acceptance criterion names
  `/wizard/subscriptions?focus=<id>` explicitly, and the link does land on the
  right page, but none of the three wizard pages read a `focus` query param
  today. Wiring highlight/scroll into `views/subscriptions/`,
  `views/personal_loans/` and `views/safety_funds.py` is outside this plan's
  touchpoints, so the param is left as a forward-compatible hook — worth a
  Chore-inbox line.
- **Cap, not pagination.** Out-of-scope bullet reads "Pagination; cap at ~12
  items total with a '+N more' tail" — implemented as `MAX_ROWS = 12` plus a
  `+N more` label. Grouping is by section, but the *ranked* order decides
  which section leads, so the most urgent item always brings its group to the
  top rather than a fixed section order burying an overdue loan.
- **Perf.** `detect_candidates` is the only expensive collector.
  `test_aggregates_under_200ms_on_a_thousand_transactions` pins the plan's
  budget with a real 1 000-row insert.

### BDD

New `## Feature: Wizard Action Items`, KAL-WAC-001..005. 002/003/004 are
`@automated` via `tests/e2e/test_wizard_actions_widget.py`. 001 (empty state)
and 005 (both widget sizes) are `@manual`: the e2e suite shares one database
across the whole session, so "no wizard section has an open item" cannot be
guaranteed at the point this test runs, and asserting it would make the suite
order-dependent.
