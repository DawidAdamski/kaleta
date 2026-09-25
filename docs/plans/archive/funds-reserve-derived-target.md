---
plan_id: funds-reserve-derived-target
title: Reserve funds — target derived from 12-month average spending
area: budgets
effort: small
status: archived
archived_at: 2026-09-25
roadmap_ref: ../../roadmap.md#budgets
---

# Reserve funds — target derived from 12-month average spending

Gap-closing plan for issue #13 (`KAL-FND-002`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-FND-001` and
`KAL-FND-003` are `@automated`; this is the last gap.

## Intent

"A 3-month reserve" should mean three months of *what I actually
spend*, not a number typed into the dialog.

## What exists (2026-09-23)

- `ReserveFund.emergency_multiplier` and the multiplier input
  (`views/safety_funds.py`) — it only draws tick marks on a manual
  target.
- `ReserveFundService.trailing_monthly_expense` averages **90 days** and
  feeds "months of coverage"; the what-if simulator shares it.

## Scope

- `ReserveFundService.derived_target(fund)` = multiplier × average
  monthly expense over the last 12 months (non-transfer expenses);
  the dialog offers "derive from spending" vs a manual target.
- Keep one averaging function with a window parameter; do not fork the
  formula the what-if simulator depends on.

## Acceptance criteria

- `grep -qE "KAL-FND-002 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Should months of coverage also move to 12 months? Default: no — keep
  90 days there, the target uses 12; record both in the dialog's hint.

## Implementation notes

- **Persistence.** New column `reserve_funds.target_from_spending`
  (bool, default false; migration `n8o9p0q1r2s3`). The target is
  recomputed live in `ReserveFundService.with_progress`, so the Reserves
  panel, the dashboard below-target warning (`WizardActionService`) and
  the progress bar all use the derived figure. On every create/update the
  service also snapshots the derived target into `target_amount`, so
  readers that take the column raw (wizard projection's monthly
  contribution, `GET /api/v1/reserve-funds`) see the figure as of the last
  save instead of the stale manual number.
- **One formula.** `trailing_monthly_expense` gained `window_days` /
  `window_months` parameters (defaults unchanged: 90 days / 3). The
  12-month window is `TARGET_WINDOW_DAYS = 365` /
  `TARGET_WINDOW_MONTHS = 12`, reached through
  `target_monthly_expense()`. The what-if simulator's call is untouched.
- **Open question resolved (default taken).** Months of coverage stays on
  90 days; the target uses 12 months. The dialog hint states both.
- **Validation.** `target_from_spending` needs `emergency_multiplier`:
  the schema rejects it on create, the service raises
  `kaleta.exceptions.ValidationError` when a PATCH would leave a derived
  fund without one. The dialog only offers the switch for emergency funds.
- **Tests.** The BDD literals (5200.00 → 15600.00) are asserted in
  `tests/unit/services/test_reserve_fund_service.py::TestDerivedTarget`
  on an isolated in-memory DB. The e2e test covers the dialog wiring only
  and compares the card with the hint, because the e2e DB is shared
  across tests and its 12-month average is not under the test's control.
- **Review nits (accepted, not changed).** (1) The schema requires a
  multiplier, not `kind == EMERGENCY`, for `target_from_spending` — the
  plan defines the target by the multiplier; only the dialog limits the
  switch to emergency funds. (2) `list_with_progress` re-runs the 12-month
  aggregate once per derived fund; logged in `chores.md`, negligible at
  one or two funds.

## Implementation

Landed on 2026-09-25 (PR #141).

| SHA | Author | Date | Message |
|---|---|---|---|
| `498237c` | Dawid Adamski | 2026-09-25 | Merge pull request #141 from DawidAdamski/plan/funds-reserve-derived-target |

**Files changed:**
- alembic/versions/n8o9p0q1r2s3_reserve_fund_target_from_spending.py
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/funds-reserve-derived-target.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/reserve_fund.py
- src/kaleta/schemas/reserve_fund.py
- src/kaleta/services/reserve_fund_service.py
- src/kaleta/views/safety_funds.py
- tests/e2e/test_reserve_funds.py
- tests/unit/services/test_reserve_fund_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
