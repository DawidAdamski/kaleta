---
plan_id: transactions-colored-amounts
title: Transactions — coloured amounts + global colour tokens
area: transactions
effort: small
status: archived
archived_at: 2026-04-22
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Transactions — coloured amounts + global colour tokens

## Intent

Make transaction kind instantly readable via colour. Reuse the exact
scheme already used on Planned Transactions so the user sees the same
semantic colours everywhere in the app — expense = red, income =
green, transfer = neutral.

## Scope

- Colour the amount cell on the Transactions table by kind.
- Extract a single shared helper (module in `views/` or `theme.py`)
  that returns the colour class for a given `(kind, amount)` pair.
- Audit and migrate any ad-hoc colouring in other views to use the
  helper (Planned Transactions, Budgets, Dashboard recent-tx widget,
  Reports where applicable).

Out of scope:
- Colouring icons or row backgrounds — only the amount text for now.
- Accessibility tokens beyond red/green (colour-blind mode is a
  follow-up).

## Acceptance criteria

- Income rows: amount rendered in the income-green token.
- Expense rows: amount rendered in the expense-red token.
- Transfer rows: amount rendered in the neutral token.
- Dark mode: colours are legible on slate-800 surfaces (use the
  existing `text-green-7/8`, `text-red-7/8`, etc. overrides in
  `theme.py`).
- The same tokens are used in Planned Transactions, Dashboard recent
  transactions, and any other view that currently duplicates this
  logic.

## Touchpoints

- `src/kaleta/views/theme.py` — add `AMOUNT_INCOME`, `AMOUNT_EXPENSE`,
  `AMOUNT_NEUTRAL` constants or a helper fn.
- `src/kaleta/views/transactions.py` — apply the classes on the
  amount column.
- `src/kaleta/views/planned_transactions.py` — migrate to shared
  helper.
- `src/kaleta/views/dashboard.py` — migrate recent-tx table.
- Any other view touching transaction amount rendering.

## Open questions

- Should neutral transfers show a small ↔ icon to make the colour
  neutrality intentional? Defer unless users report confusion.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4317f40` | Dawid | 2026-04-22 | feat: dashboard command center, reports library, forecast presets, and plan-driven features |

**Files changed:**
- src/kaleta/views/theme.py
- src/kaleta/views/transactions.py
- src/kaleta/views/planned_transactions.py
- src/kaleta/views/dashboard.py

**Notes:** Shared amount-colour helpers landed in `theme.py`; Transactions, Planned Transactions, and Dashboard recent-tx rendering were migrated to the shared tokens.
