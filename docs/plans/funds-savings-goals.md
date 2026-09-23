---
plan_id: funds-savings-goals
title: Savings goals (skarbonki) on reserve funds — target date, contributions, pace, release
area: budgets
effort: medium
status: draft
roadmap_ref: ../roadmap.md#budgets
---

# Savings goals (skarbonki) on reserve funds

Gap-closing plan for issue #12 (`KAL-GOL-001`…`004`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md).

## Intent

A skarbonka is a `ReserveFund` of kind `VACATION` with a target; the
Safety & Reserve Funds page already creates one, shows balance / target
and a percentage, and archives it. What a goal needs on top is a date,
a way to put money in, the pace to get there, and a clean close.

## What exists (2026-09-23)

- Create dialog with kind, name, target; card with `balance / target`
  and `%` (`views/safety_funds.py`); `ReserveFundService.archive` and an
  "Archived funds" section. Service tests only, no e2e.
- **Blocker:** a fund's balance is its backing account's
  `Account.balance`, which no transaction moves (chore inbox,
  2026-09-23) — so GOL-002 "record a contribution" cannot show up.

## Scope

- `ReserveFund.target_date` (nullable) + migration; schema, dialog
  (GOL-001). Decide whether "Goals" is its own route or a filter of the
  funds page; reword GOL-001's "Goals page" to match.
- Contribution action = a transfer into the backing account (GOL-002),
  once balances follow transactions.
- Pace: `(target − saved) / months left`, shown on the card (GOL-003).
- Close: archive + optional transfer of the balance back to a chosen
  account (GOL-004).

## Acceptance criteria

- `grep -cE "KAL-GOL-00[1-4] @automated" docs/bdd.md | grep -q '^4$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Own page or funds-page filter? Default: filter on the existing page,
  scenario reworded — one place for all funds (see
  `funds-reservoir-view`).
