---
plan_id: seed-payment-calendar
title: Seed — populate payment calendar with planned transactions
area: seed
effort: small
roadmap_ref: ../roadmap.md#payment-calendar
status: draft
---

# Seed — populate payment calendar with planned transactions

## Intent

`/payment-calendar` consumes the `PlannedTransaction` table via
`PlannedTransactionService.get_occurrences()`. After running
`scripts/seed.py` the table is empty, so the page renders an
empty grid for new users — even though the demo dataset has
six years of historical transactions. Seed a realistic set of
recurring planned entries so the calendar, dashboard "upcoming"
widgets, and the forecast all have something to render on a
fresh install.

## Scope

- **New seed block** in `scripts/seed.py` between the budgets
  and the physical assets sections, creating ~12 planned
  transactions whose recurrence covers the next 60 days:
  - **Rent** — monthly, `start_date = first day of next month`,
    amount = current `BASE_BUDGETS["Mieszkanie & Czynsz"]`,
    category = *Mieszkanie & Czynsz*, account = checking.
  - **Utilities** — monthly, day 12, amount ≈ 280 zł,
    category = *Media*, account = checking.
  - **Internet** — monthly, day 8, amount = 79 zł,
    category = *Media*, account = checking.
  - **Phone** — monthly, day 22, amount = 49 zł, category =
    *Subskrypcje → Miesięczne*, account = checking.
  - **Netflix / Spotify / YouTube Premium / iCloud / ChatGPT** —
    monthly, varied days (3, 7, 14, 18, 27), amounts 22 / 23 /
    35 / 8 / 99 zł, category = *Subskrypcje → Miesięczne*,
    account = credit.
  - **Salary** — monthly, day 1, amount = `salary_for_month(0)`,
    category = *Wynagrodzenie*, account = checking, type =
    INCOME, name = "Wynagrodzenie".
  - **Quarterly insurance** — quarterly, next quarter start,
    amount = 420 zł, category = *Inne wydatki*, account =
    checking.
  - **Yearly domain renewal** — yearly, on a fixed date next
    year, amount = 60 zł, category = *Subskrypcje → Roczne*,
    account = credit.
  - **Once-off doctor visit** — once, in 9 days, amount =
    180 zł, category = *Zdrowie & Apteka*, account = cash.
- All entries have `is_active=True`, `interval=1`, and meaningful
  `name` (used as the calendar label) and `description`.
- Imports — `PlannedTransaction`, `RecurrenceFrequency` from
  `kaleta.models.planned_transaction`.
- Print line — extend the seed summary with `… N planned
  transactions`.

Out of scope:
- A "subscriptions row → planned transaction" sync — they
  already share the Subscriptions root via the wizard
  projection service; no need to duplicate.
- Tagging the planned rows (the model has no tags).
- Linking generated occurrences to historical transactions
  (handled by the dedicated subscriptions / dedupe pipeline).

## Acceptance criteria

- After re-running `uv run python scripts/seed.py`, the
  Payment Calendar page on a brand-new install shows
  occurrences across the next 60 days.
- The dashboard "upcoming" widget (if present) renders the
  same items.
- The forecast page reflects planned cashflow on the right
  edge of the chart.
- Reseeding is idempotent (drop_all + create_all already
  happens at the top of `seed`).

## Touchpoints

- `scripts/seed.py` — new block + summary print update.
- `README.md` — bump the demo summary count.
- No model / migration change.

## Open questions

1. **How many subscriptions?** Default: **5** matching the
   payee plan above so payee links and subscriptions
   intersect cleanly.
2. **Currency** — `PlannedTransaction` has no `currency` field;
   default currency is implied. Ignore.
3. **Should we link planned → category for transfers?** Default:
   no — keep it expense / income only; transfers are not
   typically "planned" from the user's perspective.

## Implementation notes
_Filled in as work progresses._
