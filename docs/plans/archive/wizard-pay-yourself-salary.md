---
plan_id: wizard-pay-yourself-salary
title: Wizard — "pay yourself a salary" panel for irregular income
area: wizard
effort: medium
status: archived
archived_at: 2026-09-09
roadmap_ref: ../../roadmap.md#cross-cutting-principles
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

### Resolved open questions

1. **Which incomes count** — took the plan default: **all non-transfer
   `INCOME` transactions, across every account**. The category filter
   was left out entirely rather than shipped as an unused service
   parameter; the plan lists it as a stretch, and adding a knob nothing
   calls is worse than adding it when the panel needs it.
2. **Proposal formula default** — took the plan default: **worst month
   of the window**, which is what the wizard tile already promises. The
   lower quartile and median ship as selectable alternatives
   (`SalaryBasis`), and the amount stays editable on top of either.

### Decisions worth a reviewer's time

- **Where the series starts.** The window is N *complete* months (the
  running month is partial and would drag every statistic down), but
  the series does not start at the window's first month — it starts at
  the first month inside the window that earned anything. Leading empty
  months are absence of data, not zero-income months; starting at the
  window edge would make the worst month `0.00` for anyone with less
  than N months of history, which is the exact case this panel exists
  for. Gaps and trailing months *after* that first earning month do
  count as zero — a dry month is real information about how far the
  income can fall.
- **Percentile definition.** `_percentile` uses the ordinary linear
  interpolation ("rank `q × (n−1)`, blend the neighbours"), so p25 and
  the median are meaningful on the short series this panel usually
  sees. For 6/9/4/12 that yields p25 = 5,500.00 and median = 7,500.00.
- **No proposal, no projection.** Under `MIN_HISTORY_MONTHS` (3) the
  service returns `salary = 0.00`, an empty `projection` and
  `has_enough_history = False`; the panel renders the hint. What gates
  the projection is whether a salary was *decided*, not whether it is
  above zero — so an explicit override always projects, `0.00` included
  (paying yourself nothing is a choice, and the resulting "every zloty
  accumulates" curve is a real answer). A user who knows better than the
  short window is never blocked.
- **The target account lives in the description.** `PlannedTransaction`
  carries a single `account_id` — there is no destination column. The
  salary transfer is therefore created on the *source* account with
  `description = "<source> → <target>"`. The plan forbids new
  scheduling machinery, so this is the honest limit of reuse; a proper
  two-legged planned transfer is a separate model change.
- **The `is_internal_transfer` filter is not redundant.**
  `TransactionCreate` rejects the flag on a non-transfer row, but the
  column carries no such constraint and both the importer and the demo
  generator write `Transaction` rows directly. The query filters on the
  flag rather than trusting the schema invariant; a unit test seeds such
  a row through the ORM to prove the guard is live.

### Where the KAL-SAL scenarios are covered

`scripts/spec_coverage.py` only reads `tests/e2e` and `tests/integration`.
The five scenarios are arithmetic over a fixed income window, and the e2e
instance shares **one** database across all modules — the panel aggregates
income from every account, so any other module's seeded income would move
the numbers on screen. Scenario coverage therefore lives in
`tests/integration/test_pay_yourself_salary.py`, pinned to a fixed
"today". `tests/e2e/test_pay_yourself_salary.py` stays a smoke test: the
tile opens the page and the panel renders, with no amount assertions.
`tests/unit/services/test_salary_service.py` covers the helpers and the
edge cases (year-end month arithmetic, dry months, multi-currency,
negative buffers, rejected inputs).

### Not done, deliberately

- No sidebar entry in `views/layout.py` — the plan scopes the route to
  `_STEP_ROUTES` only, and `KAL-NAV-004` walks every sidebar entry.
- No currency conversion. Multi-currency income is summed as-is behind a
  warning, per the plan's "warn otherwise".

## Implementation

Landed on 2026-09-09 (PR #85).

| SHA | Author | Date | Message |
|---|---|---|---|
| `c417f97` | Dawid Adamski | 2026-09-10 | Merge pull request #85 from DawidAdamski/plan/wizard-pay-yourself-salary |

**Files changed:**
- docs/bdd.md
- docs/plans/wizard-pay-yourself-salary.md
- docs/product/financial-wizard.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/main.py
- src/kaleta/schemas/salary.py
- src/kaleta/services/__init__.py
- src/kaleta/services/salary_service.py
- src/kaleta/views/wizard.py
- src/kaleta/views/wizard_salary.py
- tests/e2e/test_pay_yourself_salary.py
- tests/integration/test_pay_yourself_salary.py
- tests/unit/services/test_salary_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
