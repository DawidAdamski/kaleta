---
plan_id: subscriptions-panel-gaps
title: Subscriptions panel — monthly-total formula, cancel as of a date, cancelled section
area: transactions
effort: small
status: in-progress
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

## Implementation notes

- **Open question (59.85 vs 59.99)**: took the default. The scenario is
  right and the code changed: `_to_monthly` counts cadences in
  `MONTHLY_CADENCE_RANGE` (27–33 days) as the amount itself and cadences
  in `YEARLY_CADENCE_RANGE` (350–380) as amount ÷ 12. Any other cadence
  keeps `amount × 30 / cadence_days`. These are the ranges the view's
  `cadence_label` already used to print "Monthly" / "Yearly", so what is
  labelled yearly is also counted as a twelfth. `cadence_label` now
  imports the ranges instead of repeating them. The pinning test
  `test_yearly_sub_normalises_to_thirty_over_cadence` became
  `test_odd_cadence_normalises_to_thirty_over_cadence` (90 days → 30/mo),
  and the 49.99 + 120.00 = 59.99 case lives in
  `tests/integration/test_subscriptions_panel.py`. `scripts/spec_coverage.py`
  only scans `tests/e2e` and `tests/integration`, and the e2e database is
  shared across tests, so the exact total cannot be asserted there.
- **Cancel as of a date**: `cancel(sub_id, effective_on=…, today=…)`.
  `cancelled_at` now means "effective from", so no migration was needed.
  A date on or before today cancels at once (the old behaviour, and still
  the default). A later date keeps `status=active` and stamps
  `cancelled_at`. `totals()` excludes a row from the date it takes effect,
  and `settle_due_cancellations()` flips due rows to `cancelled` (clearing
  `next_expected_at`). The page calls it on load. `reactivate` already
  clears `cancelled_at`, so it also drops a scheduled cancellation. Other
  readers see a due row as active until the next settle; that is recorded
  in `chores.md`.
- **UI**: the cancel icon opens a dialog with a date field (default today).
  An active row with a scheduled date shows "Cancels dd.mm.yyyy". Cancelled
  rows moved out of "All subscriptions" into a "Cancelled" card below it,
  which renders only when something is cancelled.
- **KAL-SUB-004 wording**: the scenario said "mark it cancelled as of end
  of this month → it moves to the cancelled section", which contradicts
  the plan's "a future date keeps the row active and counted until then".
  I rewrote it with fixed dates (15 April → 30 April) so both halves can be
  checked with BDD literals.
- Out of scope, sent to `chores.md`: the wizard projection's separate
  30/365 amortisation.
