---
plan_id: subscriptions-panel-gaps
title: Subscriptions panel — monthly-total formula, cancel as of a date, cancelled section
area: transactions
effort: small
status: draft
roadmap_ref: ../roadmap.md#transactions
---

# Subscriptions panel — monthly-total formula, cancel as of a date, cancelled section

Gap-closing plan for issue #8 (`KAL-SUB-002`, `KAL-SUB-004`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md). `KAL-SUB-001` and
`KAL-SUB-003` are `@automated`.

## What exists (2026-09-23)

- Monthly total on `/wizard/subscriptions` from
  `SubscriptionService.totals`; `_to_monthly` is `amount × 30 /
  cadence_days`, so 49.99 monthly + 120.00 yearly (365 days) shows
  **59.85**, not the scenario's **59.99** (`120 / 12`). A unit test
  (`test_yearly_sub_normalises_to_thirty_over_cadence`) pins the 30/365
  formula.
- Cancel action stamps *today*; cancelled rows stay in the one "All
  subscriptions" card with a grey badge; totals already skip them.

## Scope

- **SUB-002** — decide the normalisation: yearly ÷ 12 (and monthly × 1)
  for the canonical cadences, `30 / cadence_days` only for odd
  cadences. Update the pinning unit test with the decision.
- **SUB-004** — `cancel(effective_on=...)`: a future date keeps the row
  active and counted until then; a "Cancelled" section below the active
  list.

## Acceptance criteria

- `grep -qE "KAL-SUB-002 @automated" docs/bdd.md`
- `grep -qE "KAL-SUB-004 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Is 59.85 acceptable and the scenario wrong? Default: no — people read
  a yearly bill as "a twelfth a month"; change the code.
