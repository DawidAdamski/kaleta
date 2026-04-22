---
plan_id: wizard-getting-started-mentor
title: Getting Started — expand into contextual mentor
area: wizard
effort: small
status: draft
roadmap_ref: ../product/financial-wizard.md#1-getting-started
---

# Getting Started — expand into contextual mentor

## Intent

The Getting Started card today stops at "you've set everything up".
Expand it into a contextual mentor that, post-setup, points the user
to the right view/dashboard for whatever they are currently trying to
do. Stay ambient — not a nag.

## Scope

- After all 4 setup steps complete, the card flips into "mentor"
  mode: a rotating set of short suggestions (1 visible at a time)
  linking into the right view.
- Suggestions are evaluated against current app state — not random.
  Examples:
  - "You just imported 120 transactions — categorise them in
    Transactions." (when un-categorised > threshold)
  - "Budgets defined — pin Budget Progress to Dashboard." (when
    budgets exist and the widget is not pinned)
  - "Net worth has grown 5% this month — see Net Worth."
    (when applicable)
- User can dismiss a suggestion (per-session or permanently).

Out of scope:
- LLM-generated suggestions (paid-tier feature, later).
- Push notifications from the mentor (uses the notification
  infrastructure delivered by `wizard-monthly-readiness`).

## Acceptance criteria

- With all setup done, the card shows the "All done!" badge AND
  rotates through at least one matching suggestion.
- Each suggestion has a primary CTA that routes to the relevant
  page.
- Dismissing a suggestion removes it for the current session
  (minimum) or forever (if user chose so).
- No suggestion fires when its precondition is unmet.

## Touchpoints

- `src/kaleta/views/wizard.py` — mentor rendering inside the
  onboarding card.
- New `src/kaleta/services/wizard_service.py` (or similar) —
  rule engine that returns eligible suggestions for current state.
- `src/kaleta/i18n/locales/*` — suggestion text + CTAs.
- `app.storage.user["wizard_mentor_dismissed"]` — persistence.

## Open questions

- Should suggestions be defined in code (type-safe, tight coupling)
  or data (JSON/YAML, easier iteration)? Lean on code for v1.
- How many suggestions should rotate before the user sees a
  repeat? v1: one at a time, no rotation until dismissed.

## Implementation notes

_(filled as work progresses)_
