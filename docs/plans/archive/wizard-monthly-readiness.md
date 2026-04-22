---
plan_id: wizard-monthly-readiness
title: Wizard — Monthly Readiness section
area: wizard
effort: large
status: archived
archived_at: 2026-04-23
roadmap_ref: ../../product/financial-wizard.md#2-monthly-readiness
---

# Wizard — Monthly Readiness section

## Intent

At the turn of each month, a user has a short checklist of things to
do to stay in control: close last month, confirm income landed,
allocate the new month's budget, acknowledge upcoming bills. Today
this is invisible. Give the user a single "ready for the month" flow
that runs on a monthly cadence.

## Scope

Monthly Readiness wizard section with 4 stages, each with a clear
done-state:

1. **Close last month** — verify all imports done, categorise
   stragglers, reconcile at least checking account. "Close month"
   action stamps a month-end snapshot.
2. **Confirm income** — list expected income from recurring rules
   vs what actually landed; flag gaps.
3. **Allocate new month** — copy previous month's budgets forward
   (with per-category edits if desired); YNAB-style envelope option
   available.
4. **Acknowledge upcoming bills** — show this month's planned
   transactions; user ticks off "seen".

Cross-cutting:
- Notification infrastructure: an in-app notification (with opt-in
  email in a future pass) fires on the 1st of each month to nudge
  the user into the section.
- AI-generated month-ahead narrative is a paywalled feature —
  surfaced here as a locked teaser; actual generation lives in a
  later plan.

Out of scope:
- Email / push delivery — scaffold the service boundary, v1 is
  in-app only.
- The AI narrative generator itself.

## Acceptance criteria

- Opening the wizard on the 1st of any month shows a highlighted
  "Monthly Readiness" card with stage-1 active.
- Each stage has an explicit completion gesture; progress persists
  per user per `YYYY-MM` key.
- "Copy budgets forward" creates new `Budget` rows for the new month
  with the same amounts as the prior month, respecting per-category
  overrides the user sets during the flow.
- Completing all 4 stages stamps `month_ready[YYYY-MM] = true` and
  collapses the card.

## Touchpoints

- `src/kaleta/services/monthly_readiness_service.py` — new service
  with stage evaluators and `mark_ready` method.
- `src/kaleta/services/budget_service.py` — `copy_forward` helper.
- `src/kaleta/services/notification_service.py` — new skeleton
  (in-app only), used later by other plans.
- `src/kaleta/models/month_snapshot.py` — month-close snapshot for
  audit.
- Alembic migration.
- `src/kaleta/views/wizard.py` — section render.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Month-close trigger date: user-configurable (1st vs 5th) or fixed?
  v1: fixed to the 1st; read date from UTC local.
- Paywalled AI teaser: show always, or only for users who've passed
  N months of healthy use? v1: always, with a "Coming soon" tag.

## Implementation

**Shipped 2026-04-23.**

| SHA | Author | Date | Message |
|---|---|---|---|
| `5024884` | Dawid | 2026-04-23 | feat(wizard): Monthly Readiness — 4-stage close & allocate flow |

**Files changed:**
- `src/kaleta/models/monthly_readiness.py` (new, single row per `(year, month)` with 4 stage booleans + `ready_at` + `seen_planned_ids` JSON)
- `src/kaleta/models/__init__.py` (exports)
- `alembic/versions/c8e5b2a9f3d1_add_monthly_readiness.py` (new migration)
- `src/kaleta/schemas/monthly_readiness.py` (response + 4 stage payload schemas)
- `src/kaleta/services/monthly_readiness_service.py` (CRUD + 4 stage evaluators + `apply_stage_3` + `set_seen`)
- `src/kaleta/services/budget_service.py` (new `copy_forward(from_ym, to_ym, overwrite=False)` + `list_for_month`)
- `src/kaleta/services/__init__.py` (exports)
- `src/kaleta/views/monthly_readiness.py` (new `/wizard/monthly-readiness` page — 4 stacked stage cards)
- `src/kaleta/views/budget_plan.py` (adds a toolbar month picker + **Copy from previous month** button wired to `copy_forward`)
- `src/kaleta/views/wizard.py` (`_STEP_ROUTES` now maps `next_month` → `/wizard/monthly-readiness`)
- `src/kaleta/main.py` (registers the new view)
- `src/kaleta/i18n/locales/en.json`, `src/kaleta/i18n/locales/pl.json` (new `monthly_readiness.*` block + `budget_plan.copy_forward_*` keys)
- `docs/bdd.md` (new "Feature: Monthly Readiness" with 7 scenarios)
- `tests/unit/services/test_monthly_readiness_service.py` (20 tests: copy-forward invariants, stage evaluators, seen-state persistence, year-roll edge cases)

**What shipped:**
- **Stage 1 — Close last month**: counts last-month uncategorised, non-transfer transactions; deep-link to `/transactions` for review.
- **Stage 2 — Confirm income**: for each recurring income `PlannedTransaction` occurring in the window, shows expected vs actual income total (v1 uses a proportional split of the window's actual income).
- **Stage 3 — Allocate this month**: diffs previous-month → current-month Budgets, writes only the missing categories. Existing targets are preserved by default (`overwrite=False`).
- **Stage 4 — Acknowledge upcoming bills**: lists planned expenses due this month with per-row "seen" checkboxes persisted as a JSON blob on the readiness row.
- **Bonus scenario win:** implemented the long-dormant BDD scenario `Copy previous month budget to current month` (`docs/bdd.md`, Annual Budget Planning) with a month-picker + button on `/budget-plan`. The i18n key `budget_plan.copy_from` was already present; the button is now wired.

**Partial coverage (flagged for follow-up):**
- **Month-end snapshot model** — not shipped; no BDD scenario depended on it and nothing downstream reads it yet.
- **Notification infrastructure** — not shipped; no scenario exercises timed nudges. The wizard row surfaces the entry card whenever the user opens `/wizard`.
- **YNAB envelope allocation in Stage 3** — deferred; `overwrite=False` copy-forward is the v1 allocation story.
- **Stage 2 actual-to-plan matching** — v1 proportional split is naive; a future pass will match by description or a dedicated FK from Transaction → PlannedTransaction.
- **AI month-ahead narrative teaser** — not shipped as a locked chip; defer until the wider AI surface lands.
- **Full reconciliation** in Stage 1 — separate plan; v1 surfaces uncategorised count only.
