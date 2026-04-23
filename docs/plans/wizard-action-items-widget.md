---
plan_id: wizard-action-items-widget
title: Dashboard — Wizard action-items widget
area: wizard
effort: small
roadmap_ref: ../product/financial-wizard.md#shared-wizard-patterns
status: draft
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
_Filled in as work progresses._
