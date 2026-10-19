---
plan_id: projection-subscription-monthly
title: Budget-builder projection normalises a subscription like the panel does
area: services (wizard projection / subscriptions)
effort: small
status: archived
archived_at: 2026-10-19
roadmap_ref: ../../roadmap.md
---

# Budget-builder projection normalises a subscription like the panel does

## Intent
Chore-inbox fix (spotted during `subscriptions-panel-gaps`). Two code paths turn
a subscription into a monthly figure, and they disagree:

- **The Subscriptions panel** uses `subscription_service._to_monthly`: a monthly
  bill counts in full, a **yearly bill as a twelfth** (`amount / 12`,
  `KAL-SUB-002`), and only an odd cadence falls back to the 30-day
  approximation.
- **The budget-builder projection** uses
  `wizard_projection_service._monthly_from_subscription`, which **always**
  computes `amount × 30 / cadence_days`.

So a yearly domain bill of 120.00 reads **10.00/mo** in the panel but
**9.86/mo** (120 × 30 / 365) in the budget builder — and even a monthly bill
whose cadence is 31 rather than 30 drifts (full amount in the panel, `× 30/31`
in the builder). The same subscription shows two different monthly costs
depending on the screen, because the cadence logic is duplicated and the two
copies diverged.

This slice points the projection at the panel's `_to_monthly`, so both screens
normalise a subscription the same way.

## Scope
`KAL-SUB-009` only: the budget-builder projection normalises a subscription with
the same rule the panel uses.

- **`wizard_projection_service._monthly_from_subscription`**
  (`src/kaleta/services/wizard_projection_service.py`): delegate to
  `subscription_service._to_monthly(abs(sub.amount), sub.cadence_days)` and
  quantise the result to 0.01 (the projection's existing precision). This
  removes the second, divergent cadence formula; the shared
  `MONTHLY_CADENCE_RANGE` / `YEARLY_CADENCE_RANGE` now govern both screens.
- **BDD**: new `KAL-SUB-009` scenario in `docs/bdd.md` (`@automated`).
- **Tests** (`tests/unit/services/test_wizard_projection_service.py`): update the
  two cases that encode the old 30-day formula for a yearly bill
  (`test_monthly_from_subscription_yearly`, the pure helper, and
  `test_yearly_subscription_amortised_to_monthly`, through
  `get_budget_builder_sources`) to assert the twelfth — a yearly 120.00 at a
  365-day cadence projects to 10.00, the panel's figure and the `KAL-SUB-002`
  literal. The scenario's cover lives in `tests/integration/` (a new
  `test_wizard_projection.py`), since `scripts/spec_coverage.py` only scans
  `tests/e2e` and `tests/integration`, not `tests/unit`; the unit cases stay as
  fast helper-level checks (including a `cadence_days=31` monthly case).

**Not in scope (binding):**
- `_subscription_cadence_label` inlines the same 27–33 / 350–380 day ranges as
  the shared constants. Pointing it at `MONTHLY_CADENCE_RANGE` /
  `YEARLY_CADENCE_RANGE` too is a zero-behaviour consolidation, but it is the
  cadence *label*, not the monthly *amount* this fix is about — left for a
  separate line so the diff stays single-purpose.
- No change to `_to_monthly` itself, to the panel, or to how subscriptions are
  stored. No view or API change (the projection is a service; the budget-builder
  view reads it unchanged).

## Acceptance criteria
- `uv run pytest tests/unit/services/test_wizard_projection_service.py -q`
- `grep -q "KAL-SUB-009 @automated" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`

Fail-on-old: before this slice `_monthly_from_subscription` returns
`120 × 30 / 365 = 9.86` for a yearly 120.00 bill, so the updated assertions
(10.00, the panel's twelfth) fail on the old code and pass on the new. The
monthly case (49.99 at a 30-day cadence → 49.99) is unchanged and stays green.
Expected values are the `KAL-SUB-002`/`-009` literals (120.00 → 10.00).

## Touchpoints
- `src/kaleta/services/wizard_projection_service.py`
- `tests/unit/services/test_wizard_projection_service.py`
- `tests/integration/test_wizard_projection.py`
- `docs/bdd.md`

## Open questions
- None blocking. Resolved in decisions below.

## Implementation notes
- **Decision — delegate, don't re-copy the ranges.** The bug is a second copy of
  the cadence logic that drifted; importing `_to_monthly` removes the copy
  rather than adding a third. `wizard_projection_service` already imports a
  sibling service module (`text_order`), and `subscription_service` does not
  import it back, so there is no cycle and the service→service import respects
  the layering.
- **Decision — the two yearly tests move to the twelfth.** They asserted
  `365 × 30 / 365 = 30.00`, a value rigged so the buggy 30-day formula happened
  to look round; under the correct rule a yearly bill is `amount / 12`. The
  tests now use the panel's own example (120.00 → 10.00) so the literal is the
  `KAL-SUB-002` one and the regression is unmistakable. This is a real behaviour
  change, not loosened assertions (rule 4).
- **Note — `cadence_days <= 0`.** The old helper returned `abs(amount)` for a
  non-positive cadence; `_to_monthly` returns 0. This is unreachable in
  practice — `SubscriptionCreate` constrains `cadence_days` to 1–400
  (`schemas/subscription.py`) — so the change is behaviourally inert and simply
  defers the guard to the shared helper. Recorded so the delta is not a
  surprise.
- **Note — the monthly drift too.** The bug was not only yearly: a monthly bill
  whose cadence is 31 (inside `MONTHLY_CADENCE_RANGE`) used to read `× 30/31`
  here while the panel counted it in full. A `cadence_days=31` unit case pins
  that half of the fix.
</content>

## Implementation

Landed on 2026-10-19 (PR #292).

| SHA | Author | Date | Message |
|---|---|---|---|
| `5e7518f` | Dawid Adamski | 2026-10-19 | Merge pull request #292 from DawidAdamski/fix/projection-subscription-monthly |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/projection-subscription-monthly.md
- src/kaleta/services/wizard_projection_service.py
- tests/integration/test_wizard_projection.py
- tests/unit/services/test_wizard_projection_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
