---
plan_id: funds-irregular-items
title: Irregular expenses fund — itemised yearly costs, ÷10 contribution, fund history
area: budgets
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#budgets
---

# Irregular expenses fund — itemised yearly costs, ÷10 contribution, fund history

Gap-closing plan for issue #10 (`KAL-IRR-001`…`005`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md).

## Intent

The fund container exists; the thing that makes it a *plan* does not.
The user lists yearly costs (car insurance, property tax), Kaleta
derives the monthly contribution with the ÷10 rule (two months of
slack), proposes a standing transfer, and records each payment out of
the fund against its item.

## What exists (2026-09-23)

- `ReserveFundKind.IRREGULAR` (`models/reserve_fund.py`); the wizard's
  "irregular" step routes to `/wizard/safety-funds`.
- The radar's fund line (`RadarSummary.monthly_equivalent`) is
  detected yearly costs **÷ 12**, not user items ÷ 10 (`KAL-REC-009`).
- The proposal → planned-transfer pattern exists for salary only
  (`salary_service.py`, `KAL-PYS`).
- **Blocker:** a fund's balance is `Account.balance` of its backing
  account, which no transaction moves (see the chore inbox entry of
  2026-09-23). `KAL-IRR-004` / `005` cannot hold until that is fixed or
  the fund balance is derived from transactions. Fixed by
  [`accounts-ledger-balances`](archive/accounts-ledger-balances.md); do that plan first.

## Scope

- Model `IrregularItem` (fund FK, name, yearly amount, due month,
  optional category) + migration; service CRUD; items list on the fund
  (IRR-001), fund total ÷ 10 (IRR-002).
- Funding proposal → monthly planned TRANSFER into the backing account
  (IRR-003), reusing the salary proposal pattern.
- Link a payment from the fund's account to an item; fund history marks
  unlinked payments as unplanned (IRR-004, IRR-005).
- Reconcile with the radar: the radar's fund line either feeds items or
  shows beside them — decide in this plan, do not keep two formulas.

Out of scope: gift planning (`KAL-GFT`, issue #11) feeding items.

## Acceptance criteria

- `grep -cE "KAL-IRR-00[1-5] @automated" docs/bdd.md | grep -q '^5$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- ÷10 vs ÷12: the radar uses 12. Default: ÷10 for user items as the
  scenarios say; the radar line stays an estimate.

## Implementation notes

### Delivery in two PRs

- **Part A — the plan**: `IrregularItem` (model, migration, service), the fund's own page
  with its items and the ÷10 total (`KAL-IRR-001`, `-002`), the funding proposal as a
  monthly planned transfer (`KAL-IRR-003`), and the radar on the same rule.
- **Part B — the payments**: a payment out of the fund linked to an item, the fund's
  history with unlinked payments marked unplanned (`KAL-IRR-004`, `-005`).

### Decisions (Part A)

- **One rule, ÷10, in `kaleta.core.irregular`** (open question): an item's monthly
  contribution is its yearly amount ÷ 10, rounded half-up to the grosz, and the fund's is
  the sum of its items'. The radar's fund line uses the same function instead of ÷ 12 —
  the plan says not to keep two formulas, and the radar's total is a suggestion for this
  very fund. `KAL-REC-009` pins the yearly total (unchanged); the monthly figure the radar
  prints moves from yearly ÷ 12 to yearly ÷ 10.
- **`irregular_items`**: `fund_id` (cascade with the fund), `name` (`EncryptedText`, like a
  fund's name), `yearly_amount` (> 0), `due_month` (1–12, optional: a surprise cost has
  none), `category_id` (optional, `SET NULL`; Part B's payment defaults to it). Items
  belong to an `IRREGULAR` fund only; the service refuses another kind.
- **The fund's page** is `/wizard/safety-funds/{fund_id}`, reached from an irregular
  fund's card ("Items"). The Safety Funds list keeps its cards; the plan lives on its own
  page because it grows a list, a proposal and (Part B) a history.
- **The funding proposal** follows the salary one (`KAL-SAL-004`): pick the account the
  money comes from, a start date (the first of next month), and "Create the monthly
  transfer" creates a monthly planned `TRANSFER` of the fund's contribution on that
  account, described "<source> → <fund account>". A planned transaction has no target
  account column, so the target is named in the description, as for the salary. Proposed
  only when the fund has a backing account and at least one item; the button is refused
  when a monthly transfer of the same amount and description already exists.
- **Wherever a fund's rows go, its items go**: the category merge (`DedupeService`) moves
  an item's category to the keeper, "clear all data" deletes items, and the backup carries
  the new table (its round-trip test seeds one). The example data gives "Wydatki
  nieregularne" four yearly bills.
- **Tests (Part A)**: `tests/integration/test_irregular_fund.py` (`KAL-IRR-001`…`003`,
  with the refusals: another kind of fund, a transfer from the fund into itself, the same
  transfer twice), `tests/e2e/test_irregular_fund.py` (the page from the fund's card to
  the planned transfer), `tests/unit/core/test_irregular.py` (the rule's rounding). The
  radar's unit test now expects 145.00 a month for 1450.00 a year (÷10), by the decision
  above.

### After review (Part A)

- **`KAL-REC-009` pins the radar's monthly figure** (145.00 for 1450.00 a year) now that
  it follows the fund's ÷10 rule, in the scenario and its integration test.
- **The "already planned" check reads the description** ("<source> → <fund account>"), as
  the salary's target does: after renaming an account the same transfer can be planned a
  second time. Planned transactions have no target-account column; adding one is a plan of
  its own.
- **Polish copy** after the i18n check: "Miesiąc płatności" rather than a header ending on
  "w", and no "co miesiąc … comiesięczny" twice in one sentence.
