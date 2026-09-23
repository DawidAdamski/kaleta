---
plan_id: funds-irregular-items
title: Irregular expenses fund — itemised yearly costs, ÷10 contribution, fund history
area: budgets
effort: large
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Irregular expenses fund — itemised yearly costs, ÷10 contribution, fund history

Gap-closing plan for issue #10 (`KAL-IRR-001`…`005`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md).

## Intent

The fund container exists; the thing that makes it a *plan* does not.
The user lists yearly costs (car insurance, property tax), Kaleta
derives the monthly contribution with the ÷10 rule (two months of
slack), proposes a standing transfer, and records each payment out of
the fund against its item.

## What exists (2026-09-23)

- `ReserveFundKind.IRREGULAR` (`models/reserve_fund.py`); the wizard's
  "irregular" step routes to `/wizard/safety-funds`.
- The radar's fund line (`RadarSummary.monthly_equivalent`) is
  detected yearly costs **÷ 12**, not user items ÷ 10 (`KAL-REC-009`).
- The proposal → planned-transfer pattern exists for salary only
  (`salary_service.py`, `KAL-PYS`).
- **Blocker:** a fund's balance is `Account.balance` of its backing
  account, which no transaction moves (see the chore inbox entry of
  2026-09-23). `KAL-IRR-004` / `005` cannot hold until that is fixed or
  the fund balance is derived from transactions.

## Scope

- Model `IrregularItem` (fund FK, name, yearly amount, due month,
  optional category) + migration; service CRUD; items list on the fund
  (IRR-001), fund total ÷ 10 (IRR-002).
- Funding proposal → monthly planned TRANSFER into the backing account
  (IRR-003), reusing the salary proposal pattern.
- Link a payment from the fund's account to an item; fund history marks
  unlinked payments as unplanned (IRR-004, IRR-005).
- Reconcile with the radar: the radar's fund line either feeds items or
  shows beside them — decide in this plan, do not keep two formulas.

Out of scope: gift planning (`KAL-GFT`, issue #11) feeding items.

## Acceptance criteria

- `grep -cE "KAL-IRR-00[1-5] @automated" docs/bdd.md | grep -q '^5$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- ÷10 vs ÷12: the radar uses 12. Default: ÷10 for user items as the
  scenarios say; the radar line stays an estimate.
