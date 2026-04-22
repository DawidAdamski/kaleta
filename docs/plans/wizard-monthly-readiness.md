---
plan_id: wizard-monthly-readiness
title: Wizard — Monthly Readiness section
area: wizard
effort: large
status: draft
roadmap_ref: ../product/financial-wizard.md#2-monthly-readiness
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

## Implementation notes

_(filled as work progresses)_
