---
plan_id: recurring-to-planned
title: Recurring detection — create a planned transaction, flag price drift
area: transactions
effort: medium
status: in-progress
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

## Implementation notes

- **Open question 1 — payee FK vs description:** took the default. New
  nullable `planned_transactions.payee_id` (FK `payees.id`, `SET NULL`,
  indexed; migration `q1r2s3t4u5v6`, no backfill). Payee merges
  (`PayeeService.merge`, `DedupeService.merge_payees`) re-point it, like
  they do for subscriptions. `payee_id` is on `PlannedTransactionCreate` /
  `Response` only, not `Update`: the /planned edit dialog rebuilds an
  Update from a Create dump, so putting it on Update would wipe the payee on
  every edit.
- **Open question 2 — tolerance:** took the default of 5 %
  (`PRICE_DRIFT_TOLERANCE`). The check is strictly beyond 5 %: exactly 5.00 %
  is not flagged.
- **REC-002, the shared creation path:** the radar's `_link_history` moved
  to `PlannedTransactionService.link_history`. The radar's "Plan it" and the
  new `SubscriptionService.create_planned_from_candidate` both go through
  `create` + `link_history`. The radar now records the candidate's payee on
  the plan too. `DetectorCandidate` gained `account_id` / `category_id` /
  `transaction_ids`, filled from the grouped charges: the latest charge's
  account and the most common category. Cadence 30 → monthly and 365 →
  yearly, both with interval 1. The start date is the next expected charge,
  moved forward past today (shared with "Track" via
  `_next_expected_after`).
- **REC-002, "marked as handled":** uses the same rule as a tracked
  subscription. `detect_candidates` skips the payee of every active
  expense plan, and for a plan with no payee, the merchant key of its name.
  An inactive plan does not retire a detection.
- **REC-004, what counts as a "new matching payment":** an expense that is
  not a transfer and not linked to any plan, dated on or after the day the
  plan was created (`created_at`). A linked row is either a posted
  occurrence, which is written at the planned amount, or history the
  detection handed over. It matches when it pays the plan's payee, or, for a
  plan with no payee, when the merchant key of its payee name or its
  description equals the key of the plan name. The latest such payment
  decides. After "Update plan to X" the latest payment equals the plan, so
  the flag clears by itself. No dismissal state was added.
- **Where it shows:** "Create planned transaction" sits on each row of the
  Subscriptions panel's "Detected recurring charges". The drift flag is a
  "Price changes" card on /planned, with an "Update plan to …" button
  (`PlannedPriceDriftService.accept`). No API endpoints: the scope names
  only the UI behaviour.
- **Tests:** `tests/unit/services/test_recurring_to_planned.py` (service
  layer, both scenarios) and e2e
  `test_subscriptions.py::test_detection_becomes_planned_transaction`
  (REC-002) plus
  `test_planned_transactions.py::test_amount_drift_is_flagged_and_plan_updated`
  (REC-004). The e2e names carry an `E2E` suffix, as elsewhere in the
  suite, so their payees cannot collide with the REC-001 "Netflix" fixture
  in the shared e2e database.
