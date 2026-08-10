---
plan_id: wizard-unplanned-radar
title: Wizard — unplanned expenses radar (detect irregular one-offs, convert to planned)
area: wizard
effort: medium
status: draft
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
- **Cleanup rider**: drop the global "Coming soon" badge next to the
  wizard page title (`views/wizard.py` header) — 10 of 13 tiles are
  live and the badge misleads; per-tile badges stay.

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

_Filled in as work progresses._
