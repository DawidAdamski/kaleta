---
plan_id: wizard-unplanned-radar
title: Wizard — unplanned expenses radar (detect irregular one-offs, convert to planned)
area: wizard
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#payment-calendar
---

# Wizard — unplanned expenses radar

## Intent

The wizard tile "Radar nieplanowanych wydatków" (`step_unplanned`,
monthly section) is Coming soon. Its own description is the spec:
*"Detects irregular or one-off costs from the past (car service,
dentist, school fees) that are likely to repeat — and suggests adding
them as planned transactions."* This is the biggest missing piece of
the monthly cycle: recurring-but-rare costs surprise the user because
nothing surfaces them ahead of time.

## Prior art (build on, don't duplicate)

- `subscription_service.detect_candidates()` + `DismissedCandidate`
  model — cadence detection for *monthly* recurring charges. The radar
  is the same idea at low frequency (repeats every 3–12+ months).
- BDD Feature **Recurring Payment Detection (KAL-REC)** — `@planned`
  scenarios REC-002/003 already describe "convert a detected recurrence
  into a planned transaction, keep the history link"
  (`audit-planned-vs-code.md` marks them as the gap). This plan
  implements them for the irregular case — extend the KAL-REC feature,
  do not invent a new prefix.
- Irregular Expenses Fund picker (product doc §4) expects "a list drawn
  from planned / historical transactions" — the radar's output is
  exactly that input.

## Scope

- **Detection service** (`unplanned_radar_service` or an extension of
  the subscription detector): scan transaction history for
  same-payee/similar-description expenses recurring with a gap of
  ≥ 2 months, tolerating amount drift; exclude anything already
  covered by a planned transaction, subscription, or a
  `DismissedCandidate`. Pure service, unit-testable on seeded history.
- **Radar page** at `/wizard/unplanned-radar` (route added to
  `_STEP_ROUTES`): candidate list with evidence (past occurrences,
  typical amount, estimated next date) and two actions per row —
  *add as planned transaction* (pre-filled create) and *dismiss*
  (persisted, reuses the dismissed-candidates pattern).
- **Feed the irregular fund**: from the radar, a summary line "these N
  items ≈ X/year → irregular fund suggestion" linking to Safety Funds
  (no fund logic changes here).
- **Product doc**: add a section for the radar to
  `docs/product/financial-wizard.md` (it has none today — spec-first).
- **BDD**: extend Feature: Recurring Payment Detection — implement
  `KAL-REC-002`/`KAL-REC-003` where they match, and add radar-specific
  scenarios in the next free KAL-REC numbers (grep before assigning):
  candidate detected from seeded history; dismiss persists; convert
  creates a planned transaction linked to source occurrences. Retag
  `@planned` → `@automated` as tests land.
- ~~**Cleanup rider**: drop the global "Coming soon" badge next to the
  wizard page title~~ — **already done** by `restyle-wizard-index`
  (artboard 3d), which shipped first. The per-tile badges it mentions
  are now the muted "Planned" label on each unrouted row.

Out of scope: notification/reminder channel (product doc "Shared
wizard patterns" — separate infrastructure), AI classification (paid
tier), price-drift alerts.

## Acceptance criteria

- `uv run pytest tests/unit/services -q`
- `grep -qE "KAL-REC-00[5-9]" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` With seeded history containing a yearly car-service
  expense: radar lists it with past occurrences; convert creates a
  planned transaction visible in Payment Calendar; dismissed items do
  not return.

## Touchpoints

- `src/kaleta/services/` (new radar service; possibly
  `subscription_service` refactor of shared cadence helpers)
- `src/kaleta/views/wizard.py` (`_STEP_ROUTES`, header badge)
- `src/kaleta/views/` new `wizard_unplanned_radar.py` (or package)
- `src/kaleta/models/dismissed_candidate.py` (reuse/extend `kind`)
- `docs/product/financial-wizard.md`, `docs/bdd.md`
- `tests/unit/services/`, `tests/e2e/`

## Open questions

1. Detection floor — minimum occurrences to call it a pattern?
   Default: **2 occurrences ≥ 60 days apart**, amount within ±30%.
2. Reuse `DismissedCandidate` with a `kind` column vs a new table?
   Default: **reuse with kind** (one dismissal concept in the app).

## Implementation notes

### Resolved open questions

1. **Detection floor** — took the plan default: **2 occurrences**, gaps
   **≥ 60 days**, amounts within **±30 %** of the median. Two extra
   guards fell out of testing:
   - a **450-day ceiling** on the gap. Without it, two unrelated
     expenses to the same payee three years apart looked like a
     biennial rhythm. 450 days leaves room for a yearly cost that
     drifted by ~3 months.
   - the amount tolerance is checked against the **median**, not
     pairwise. A group is rejected whole when any charge falls
     outside the band, which is what keeps "same shop, wildly
     different baskets" out of the list.
   Window is 3 years (`RADAR_WINDOW_DAYS = 1095`) so a yearly cost
   that last fired 18 months ago still has two occurrences in view.
2. **Dismissals** — took the plan default: reused
   `DismissedCandidate` with a new `kind` column
   (`subscription` | `unplanned`, migration `k5l6m7n8o9p0`). `kind`
   joins the uniqueness key, and `SubscriptionService` now filters
   every dismissal query by `SUBSCRIPTION`, so neither detector can
   silence the other. A unit test pins that behaviour.

### Decisions a reviewer should know

- **Cadence mapping.** The planner expresses recurrence as
  `(frequency, interval)`. An average gap ≥ 300 days maps to
  `YEARLY` with `interval = round(gap / 365)`; anything shorter maps
  to `MONTHLY` with `interval = max(2, round(gap / 30))`, so a
  quarterly cost becomes "every 3 months". The `MONTHLY` floor of 2
  is what stops the radar from ever emitting a monthly plan.
- **Evidence link.** Converting a candidate reuses
  `PlannedTransactionService.create` and then sets
  `Transaction.planned_transaction_id` on the source charges. No new
  column was needed: `(planned_transaction_id, date)` is already
  unique, and a charge that predates `start_date` is by definition
  history rather than a posted occurrence. `planned_with_history()`
  reads that back — it is how KAL-REC-003 is verified without
  touching the planned-transactions page. The flip side: nothing marks
  a link as the radar's, so a charge linked by hand through
  `TransactionUpdate` lands in the same list. The section is therefore
  named "Planned with linked history", not "Planned from the radar" —
  the copy claims only what the query can prove. Conversion links only
  charges *before* `start_date`, so the link and the read-back agree
  even when the user picks an earlier first-occurrence date.
- **A plan "covers" a source by name alone.** A plan carries no
  reference to what it replaces, so the exclusion matches the plan's
  name against the payee / merchant key. That is coarser than
  "already covered by a planned transaction" sounds: an unrelated
  active planned expense sharing a name suppresses the candidate.
  Restricting the match to active *expenses* at least keeps a planned
  salary from silencing a same-named payee. A real provenance column
  would fix it properly — out of scope here.
- **KAL-REC-002 stays `@planned`.** Its Given is
  "Netflix 49.99 monthly" — the *subscription* detector's convert
  action, which still only creates `Subscription` rows. Retagging it
  from radar work would have overstated coverage. KAL-REC-003 is
  generic ("a planned transaction created from a detection") and is
  now `@automated`.
- **KAL-REC-009 is covered by two tests.** The e2e instance shares
  one database across the session, so a total asserted in the browser
  would drift with whatever earlier tests seeded. The 1450.00 literal
  is asserted in `tests/integration/test_unplanned_radar_summary.py`
  (isolated DB); the e2e test asserts the fund line and its link to
  Safety & Reserve Funds.
- **No nav entry.** The plan specifies `_STEP_ROUTES` as the entry
  point, so the radar is reached from the wizard tile. `layout.py`
  was left alone.
- **Product doc renumbering.** Inserting the radar as §3 pushed
  Subscriptions and Budget Builder down a number; both kept their
  original explicit anchors (`{#3-subscriptions}`,
  `{#5-budget-builder}`) so links from archived plans still resolve.

### Out of scope, deliberately left alone

- No restore-dismissed UI. `SubscriptionService.list_dismissed` /
  `undismiss` have never had one either; adding it for the radar
  alone would have been inconsistent.
- No amount-drift alerting (KAL-REC-004) and no reminder channel —
  both listed as out of scope.

### Pre-existing finding (not fixed here)

`alembic check` against head reports four `remove_index` diffs on
`categorisation_rules`, `import_rules` and `import_runs` — model and
migration disagree on indexes created before this branch. Unrelated to
this plan and left untouched; worth a Chore-inbox line.
