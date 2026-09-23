---
plan_id: recurring-to-planned
title: Recurring detection — create a planned transaction, flag price drift
area: transactions
effort: medium
status: draft
roadmap_ref: ../roadmap.md#transactions
---

# Recurring detection — create a planned transaction, flag price drift

Gap-closing plan for issue #7 (`KAL-REC-002`, `KAL-REC-004`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md). `KAL-REC-001`,
`003`, `005`…`009` are `@automated`.

## What exists (2026-09-23)

- Detection: `SubscriptionService.detect_candidates` ("Detected
  recurring charges" on the Subscriptions panel) — "Track" makes a
  `Subscription`, not a `PlannedTransaction`.
- The radar's "Plan it" (`UnplannedRadarService.
  create_planned_from_candidate`) does create a planned transaction,
  but monthly charges are excluded from the radar by design
  (`KAL-REC-006`).
- `PlannedTransaction` has **no payee field**. Nothing matches incoming
  payments against planned transactions; detector amount buckets round
  to 1 PLN, so 49.99 → 54.99 becomes a new group, not a price change.

## Scope

- **REC-002** — "Create planned transaction" on a detected candidate,
  reusing the radar's creation path; the candidate is then handled
  (same retirement rule as tracked payees).
- **REC-004** — match a new payment to its planned transaction by
  payee/description; when the amount differs beyond a tolerance, flag it
  and offer to update the plan.

## Acceptance criteria

- `grep -qE "KAL-REC-002 @automated" docs/bdd.md`
- `grep -qE "KAL-REC-004 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Payee on `PlannedTransaction` (migration) vs matching on description.
  Default: add the payee FK — description matching is what REC-004's
  drift check would trip over.
- Tolerance for "price change": default 5 %.
