---
plan_id: wizard-pay-yourself-salary
title: Wizard — "pay yourself a salary" panel for irregular income
area: wizard
effort: medium
status: draft
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Wizard — "pay yourself a salary" (irregular income)

## Intent

The wizard tile "Wypłacaj sobie pensję" (`step_salary`, income
section) is Coming soon. Its description is the spec: *"For irregular
income: calculates a safe fixed monthly 'salary' to transfer to
yourself based on your worst recent month, letting the rest accumulate
as a buffer."* Target user: self-employed / freelancer whose inflows
vary month to month (the product doc's "entrepreneur" persona,
§4 time-off fund is the same family).

## Scope

- **Calculation service** (pure, unit-testable): from N recent months
  of income transactions (default 12, configurable on the panel):
  - monthly income series (excluding internal transfers — reuse
    `is_internal_transfer` exclusion),
  - proposed salary = a conservative percentile of that series
    (default: the minimum of the last N months; show median and p25 as
    alternatives),
  - buffer projection: given the proposed salary, how the surplus
    accumulates month over month (series for a simple chart).
- **Panel page** at `/wizard/pay-yourself` (route in `_STEP_ROUTES`):
  income variability summary (best / worst / median month), the
  proposed salary with an editable override, buffer projection chart,
  and one action: **create a monthly planned transaction** (transfer
  "salary" from business/inflow account to personal account) via the
  existing planned-transactions module — the wizard produces action
  items, it does not build new scheduling machinery.
- **Account semantics**: the user picks source and target accounts on
  the panel; nothing new on the account model.
- **Product doc**: add a "Pay yourself a salary" section to
  `docs/product/financial-wizard.md` (spec-first).
- **BDD**: new Feature (`KAL-SAL`) with `@planned` scenarios: proposal
  computed from seeded irregular income; override respected; accepting
  the proposal creates the recurring planned transaction; panel
  degrades gracefully with < 3 months of history (show hint, no
  proposal). Retag as tests land.

Out of scope: automatic execution of the transfer (planned
transactions + post-due already handle it), tax/ZUS modelling,
multi-currency income normalisation (v1: single-currency incomes,
warn otherwise), reminders.

## Acceptance criteria

- `uv run pytest tests/unit/services -q`
- `grep -q "KAL-SAL-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` With seeded irregular income (e.g. 6k/9k/4k/12k over 4
  months): panel proposes 4k, shows buffer accumulation, and one click
  creates a monthly planned transfer visible in Payment Calendar.

## Touchpoints

- `src/kaleta/services/` new `salary_service.py`
- `src/kaleta/views/wizard.py` (`_STEP_ROUTES`), new view module
- `src/kaleta/services/planned_transaction_service.py` (create hook —
  read-only reuse)
- `docs/product/financial-wizard.md`, `docs/bdd.md` (KAL-SAL)
- `tests/unit/services/`, `tests/e2e/`

## Open questions

1. Which incomes count — all `INCOME` transactions, or a user-picked
   income category subset? Default: **all income minus transfers**,
   with a category filter on the panel as a stretch.
2. Proposal formula default: worst month vs p25? Default: **worst
   month of the window** (matches the tile's own description).

## Implementation notes

_Filled in as work progresses._
