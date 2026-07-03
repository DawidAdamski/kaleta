---
plan_id: q3-views-refactor
title: Views refactor — split god-objects, shared components, retire controllers
area: views
effort: large
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Views refactor — split god-objects, shared components, retire controllers

## Intent

`views/reports_canned.py` (1 247 LOC) and `views/transactions.py`
(1 234 LOC) mix rendering, state, and business logic; four more views
exceed 600 LOC. This blocks outside contributors and makes every UI
change risky. Implements **ADR-032**: the controller layer is retired,
views call services directly, and business logic that leaked into
views moves down into services.

**Blocked by:** `q3-test-safety-net` — do not start until e2e is green.

## Scope

- New `src/kaleta/views/components/` package with shared components,
  extracted from existing duplicated code (not invented new):
  - `transaction_table` (used by transactions, subscriptions, credit,
    reports),
  - `amount_label` — semantic colouring helper (income green, expense
    red, transfer neutral) used everywhere an amount renders,
  - `filter_bar` (account/category/date-range/description),
  - `empty_state`.
- Split every view file > 800 LOC into a thin page module (routing,
  layout, wiring) + per-section component modules. Order:
  1. `transactions.py`, 2. `reports_canned.py`, 3. `import_view.py`,
  4. `settings.py`, 5. `dashboard_widgets.py`, 6. `budget_plan.py`.
  One PR per view — do not batch.
- While splitting: any computation, aggregation, or persistence found
  inline in a view moves to the owning service (with a unit test).
- ADR-032 cleanup: delete `src/kaleta/controllers/`, update the
  architecture diagram and layer description in `CLAUDE.md`,
  `AGENTS.md`, `docs/architecture.md`.
- **Not in scope:** visual redesign, new features, i18n changes beyond
  moving keys, renaming routes.

## Acceptance criteria

- No file in `src/kaleta/views/` exceeds 500 LOC.
- `grep` finds no SQLAlchemy imports and no `session` usage in
  `views/` (data access only via services).
- Amount colouring comes from the single `amount_label` component in
  all views (no local colour logic left).
- Full e2e suite green after **each** PR, not just the last one.
- `src/kaleta/controllers/` no longer exists; docs updated per
  ADR-032.
- ruff + mypy strict pass.

## Touchpoints

All of `src/kaleta/views/`, `src/kaleta/services/` (logic moving
down), `CLAUDE.md`, `AGENTS.md`, `docs/architecture.md`,
`tests/unit/` (new service tests), i18n keys move with their
components.

## Open questions

- Component API convention: plain functions returning NiceGUI
  elements vs small classes? (Suggest: functions; classes only where
  the component holds refreshable state.)
- Does `dashboard_widgets.py` split per-widget (one file each) or by
  size group?

## Implementation notes

(filled in as work progresses)
