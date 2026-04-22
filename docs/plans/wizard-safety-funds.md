---
plan_id: wizard-safety-funds
title: Wizard — Safety & Reserve Funds section
area: wizard
effort: medium
status: draft
roadmap_ref: ../product/financial-wizard.md#4-safety--reserve-funds
---

# Wizard — Safety & Reserve Funds section

## Intent

Introduce a dedicated wizard section that helps the user set up and
track dedicated reserve funds (emergency, irregular expenses,
vacation, entrepreneur buffer). Each fund has a target and a tracked
balance so the user can see coverage progress.

## Scope

- New wizard section "Safety & Reserve Funds".
- Fund types shipped as templates:
  - **Emergency** — target = 3–6× monthly expenses (user picks
    multiplier).
  - **Irregular** — target = sum of expected yearly one-offs ÷ 12 on
    a rolling horizon.
  - **Vacation** — target = user-declared yearly budget.
  - **Entrepreneur** — target = N months of business fixed costs.
- Each fund is backed by either (a) a tagged savings account, or (b)
  a virtual envelope (category-tagged balance). User picks per fund.
- Section card on the wizard shows current balance vs target with a
  progress bar and a "months of coverage" tooltip for the emergency
  fund.

Out of scope:
- Automated transfers into funds — v1 is tracking only.
- Multi-currency funds.

## Acceptance criteria

- User can create a fund from a template; target and backing mode
  are required.
- Balance updates live when the underlying account/envelope changes.
- Progress-bar logic: <50% red, 50–99% amber, ≥100% green.
- Deleting a fund never deletes transactions or accounts.

## Touchpoints

- New model `ReserveFund` (`src/kaleta/models/reserve_fund.py`)
  with fields: kind, target, backing_mode, backing_ref, created_at.
- Alembic migration.
- `src/kaleta/services/reserve_fund_service.py`.
- `src/kaleta/schemas/reserve_fund.py`.
- `src/kaleta/views/wizard.py` — new section with fund cards.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Should the emergency multiplier default to 3 or 6? v1: 3 with a
  hint that 6 is ideal.
- "Months of coverage" — denominator is trailing-90-day avg expense
  or current month's budgeted expense? v1: trailing 90-day avg, more
  stable.

## Implementation notes

_(filled as work progresses)_
