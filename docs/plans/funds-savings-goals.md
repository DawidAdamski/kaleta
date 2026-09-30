---
plan_id: funds-savings-goals
title: Savings goals (skarbonki) on reserve funds — target date, contributions, pace, release
area: budgets
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#budgets
---

# Savings goals (skarbonki) on reserve funds

Gap-closing plan for issue #12 (`KAL-GOL-001`…`004`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md).

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
  Fixed by [`accounts-ledger-balances`](archive/accounts-ledger-balances.md);
  do that plan first.

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

## Implementation notes

- **Open question (own page or filter) taken at its default.** Goals are
  a filter of Safety & Reserve Funds: an "All funds / Goals" toggle,
  `?show=goals`, one place for every fund. On the Goals filter, "Add goal"
  opens the dialog preset to a goal. KAL-GOL-001 is reworded to "filtered
  to Goals" and names the backing account the create dialog requires.
- **A goal is a `vacation`-kind fund** (`GOAL_KIND` in
  `reserve_fund_service`). Target date, Contribute, pace and Close goal
  apply to goals only; other funds keep their card and plain Archive. The
  schema refuses a `target_date` on any other kind, and an update that
  turns a goal into another kind drops its date.
- **Contribution = one internal transfer** (`create_transfer`) from a
  chosen account into the backing account, dated today. It is refused
  from the goal's own account, across currencies, or into a closed goal.
  The card moves because balances follow the ledger
  (`accounts-ledger-balances`). KAL-GOL-002 now names the source account
  and says it holds 500.00 less.
- **Pace.** `months_left` counts whole months, and a month counts once its
  day comes round (2026-07-01 → 2027-06-01 is 11; from 07-15 it is 10).
  `monthly_pace = (target − saved) / months_left`, rounded **up** to the
  grosz so paying it every month gets there. It is 0 once the goal is
  reached. With no whole month left, the whole remainder is due now. The
  footer shows "Save X a month to reach it by DATE", "X still to go by
  DATE" or "Target reached".
- **Close.** Moves the backing account's whole balance to the chosen
  account (nothing is moved if it is zero or less), then archives. The
  dialog defaults to the account of the goal's latest incoming transfer
  (`last_contribution_source`), matching "released back to the source
  account", and offers "Keep it where it is". The transfer and the
  archive are two commits: a failure between them leaves an active goal
  with its money already moved, and closing it again simply archives it.
- **No REST endpoints** for contribute/close: the plan's Scope names the
  dialog and card only.
- **Tests.** `tests/integration/test_savings_goals.py` covers the four
  scenarios at service level with the BDD literals, plus the rules and
  the pace edge cases. `tests/e2e/test_savings_goals.py` drives the UI.
  Its accounts are named "W…" so they sort after the accounts other tests
  pick from unscrolled menus in the shared e2e instance (the crowding
  found by `accounts-ledger-balances`).

