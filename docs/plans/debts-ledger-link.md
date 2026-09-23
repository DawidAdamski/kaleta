---
plan_id: debts-ledger-link
title: Debt tracking — link a loan to its transfer, keep loans out of spending
area: credit
effort: medium
status: draft
roadmap_ref: ../roadmap.md#credit
---

# Debt tracking — link a loan to its transfer, keep loans out of spending

Gap-closing plan for issue #14 (`KAL-DBT-001`, `KAL-DBT-004`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md). `KAL-DBT-002` and
`KAL-DBT-003` are `@automated`.

## What exists (2026-09-23)

- `/wizard/personal-loans`: add loan dialog → `PersonalLoanService.
  create_loan`; outstanding balance per person; repayments.
- `PersonalLoan` has **no transaction FK**; repayments create a new
  mirror transaction instead of linking an existing one.
- No report, dashboard widget or summary knows about loans.

## Scope

- **DBT-001** — `PersonalLoan.transaction_id` (nullable) + migration;
  the dialog picks an existing transaction ("yesterday's transfer");
  repayments may link an existing transaction too.
- **DBT-004** — a transaction linked to a loan is excluded from expense
  totals and shown under "Loans" in the monthly summary / money flow.

## Acceptance criteria

- `grep -qE "KAL-DBT-001 @automated" docs/bdd.md`
- `grep -qE "KAL-DBT-004 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Exclusion mechanism: flag on the transaction vs join through the loan.
  Default: join — one source of truth, no second flag to keep in sync.
