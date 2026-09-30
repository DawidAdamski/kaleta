---
plan_id: accounts-ledger-balances
title: Account balances follow the ledger — opening balance + sum of transactions
area: accounts
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#accounts
---

# Account balances follow the ledger

Promoted from the chore inbox ("Reserve fund balances never follow the
ledger", found by `plan/audit-planned-vs-code`). Blocks
[`funds-savings-goals`](funds-savings-goals.md) (GOL-002/004) and
[`funds-irregular-items`](funds-irregular-items.md) (IRR-004/005).

## Intent

A user who records an expense, an income or a transfer expects the
account's balance to move. Today it does not. `Account.balance` is a
number typed into the account form, and the only other writer is the
demo seeder. `AccountService.adjust_balance` exists, but nothing calls
it. Every screen that shows "how much is on this account" is therefore
as old as the last manual edit: the accounts list, the dashboard balance
card, net worth, the forecast start point, credit-card utilisation and
reserve-fund progress. This plan makes the balance a consequence of the
ledger.

## What exists (2026-09-30)

- `Account.balance` — `Numeric(15,2)`, written by the account form
  (`views/accounts.py`, `AccountCreate/AccountUpdate.balance`) and by
  `seeders/transactions.py` (which already derives it from the rows it
  writes: income `+`, expense `−`, transfer legs `−`/`+`).
- Readers of `Account.balance`: `account_service.py` (summary),
  `forecast_service.py:319-321`, `report_service.py:426`,
  `net_worth_service.py:263-315`, `credit_service.py:88`,
  `reserve_fund_service.py:118`, `views/accounts.py:397`,
  `views/net_worth.py`, `views/dashboard_widgets/balance_card.py`,
  `views/reports_canned/net_worth_statement.py`.
- `Transaction.amount` is always unsigned. `type` gives the sign for
  income/expense. **A leg typed `transfer` carries no direction:**
  - `create_transfer` saves the outgoing leg first, so the lower id is
    the outgoing leg, but nothing records that;
  - `pair_as_transfer` overwrites an expense/income pair to `transfer`,
    which destroys the only record of direction, and the expense can have
    the higher id;
  - the mBank import writes own-account transfers as a single `transfer`
    row with `abs(row.amount)`, so the sign is lost at import;
  - `money_flow_service` guesses direction by `src.id < dst.id`.
- Cross-currency transfers: each leg's `amount` is already in its own
  account's currency (`views/transactions/add_dialog.py`), so the sum per
  account needs no FX.

## Decision: derive, don't maintain

The balance is **computed** as `opening_balance + Σ signed amounts` of
the account's transactions. It is not a running column that every write
path has to remember to update. There are too many write paths (manual
add, edit, delete, bulk actions, import, pair/unpair, planned post-due,
splits, seeders, restore from backup), and one forgotten path means
silent drift. One grouped `SUM(CASE …) … GROUP BY account_id` per page
is cheap on SQLite and Postgres alike.

## Scope

1. **Transfer direction on the row.** New `Transaction.transfer_direction`
   (`TransferDirection` StrEnum `out`/`in`, `native_enum=False`,
   nullable). It is required by the service when `type == transfer` and
   `NULL` otherwise. Set it in every writer:
   - `create_transfer`: `out`/`in`;
   - `pair_as_transfer`: expense leg → `out`, income leg → `in`;
   - mBank import: sign of `row.amount`;
   - `seeders/transactions.py`;
   - the posted leg(s) of a planned `transfer`.

   `TransactionCreate` / `TransactionResponse` expose it.
2. **Opening balance.** Rename the column `accounts.balance` →
   `accounts.opening_balance`. The ORM attribute `Account.balance`
   disappears, so mypy finds every stale reader. The migration backfills
   `opening_balance = old balance − Σ signed ledger`, which means **no
   user sees a different current balance after upgrading**, even where
   the legacy direction backfill guesses wrong. Legacy `transfer` rows
   get a direction in the same migration: a linked pair → lower id `out`,
   higher id `in`; an unlinked row → `out` (see Open questions).
3. **One balance source.** `AccountService.balances(account_ids=None,
   *, as_of=None) -> dict[int, Decimal]` computes the derived figures in
   one query, plus `AccountService.balance(account_id)`. Every reader
   listed under "What exists" switches to it. `ReserveFundService._account_balance`
   goes through it. `adjust_balance` is deleted.
4. **Schemas/API keep the word `balance`.** `AccountResponse.balance` is
   the derived current balance. `AccountCreate.balance` is "balance
   today" and becomes the opening balance, since a new account has no
   rows. `AccountUpdate.balance` means "set the current balance to X":
   the service stores `opening_balance = X − Σ ledger`. That matches
   what the account form already asks ("Balance"), so the REST contract
   and the form label do not change.
5. **BDD.** New scenarios `KAL-ACC-005`…`010` in "Account Management"
   (written `@planned` with this plan; retagged `@automated` by it).
6. **Docs.** `docs/architecture.md` (balance is derived), and the chore
   inbox entry ticked with a pointer here.

### Not in scope

- `money_flow_service` switching from the `src.id < dst.id` guess to
  `transfer_direction`. That goes in the chore inbox, in the same commit
  as the column.
- A reconciliation UI ("statement says X, Kaleta says Y").
  `AccountUpdate.balance` is enough for now.
- Balance history / balance-at-date charts beyond the `as_of` parameter.
- Anything in the funds plans (contributions, release, pace).
- Changing the unsigned-`amount` convention.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_account_balances.py -q`
- `uv run pytest tests/integration/test_account_balances.py -q`
- `uv run pytest tests/unit/services/test_reserve_fund_service.py tests/unit/services/test_net_worth_service.py tests/unit/services/test_account_service.py -q`
- `test -z "$(grep -rn 'adjust_balance' src/)"`
- `grep -cE "KAL-ACC-0(0[5-9]|10) @automated" docs/bdd.md | grep -q '^6$'`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## BDD scenarios (to add to docs/bdd.md → Account Management)

```gherkin
  KAL-ACC-005 @planned
  Scenario: Balance follows income and expenses
    Given an account "PKO Main" opened with balance 1000.00
    When I add an expense of 200.00 and an income of 50.00 to it
    Then "PKO Main" shows balance 850.00

  KAL-ACC-006 @planned
  Scenario: A transfer moves both balances
    Given "PKO Main" with balance 1000.00 and "Oszczędności" with balance 0.00
    When I transfer 500.00 from "PKO Main" to "Oszczędności"
    Then "PKO Main" shows 500.00 and "Oszczędności" shows 500.00

  KAL-ACC-007 @planned
  Scenario: Editing or deleting a transaction moves the balance back
    Given "PKO Main" opened with 1000.00 and an expense of 200.00
    When I change the expense to 150.00
    Then "PKO Main" shows 850.00
    When I delete the expense
    Then "PKO Main" shows 1000.00

  KAL-ACC-008 @planned
  Scenario: Setting the current balance by hand
    Given "PKO Main" shows 850.00
    When I edit the account and set its balance to 900.00
    Then "PKO Main" shows 900.00
    And a later expense of 100.00 leaves it at 800.00

  KAL-ACC-009 @planned
  Scenario: Upgrading keeps every balance the user saw
    Given a database from before this change where "PKO Main" shows 1234.56
    When the app migrates it
    Then "PKO Main" still shows 1234.56

  KAL-ACC-010 @planned
  Scenario: An imported own-account transfer lowers the source balance
    Given "PKO Main" is at 1000.00 and "Oszczędności" is a registered own account
    When I import an mBank row of -300.00 to "Oszczędności"'s account number
    Then "PKO Main" shows 700.00
```

Verification tests use these literals (Working Agreement §11).
`KAL-ACC-009` is an integration test that runs the Alembic upgrade on a
database seeded at the previous head.

## Touchpoints

- Models: `models/account.py` (`opening_balance`), `models/transaction.py`
  (`transfer_direction`, `TransferDirection`).
- Migration: one new revision (column rename + add, two backfills). Use
  `migration-creator`. Use batch mode for SQLite.
- Schemas: `schemas/account.py`, `schemas/transaction.py`.
- Services: `account_service.py`, `transaction_service.py`
  (`create_transfer`, `pair_as_transfer`, validation),
  `import_service.py`, the planned post-due path,
  `forecast_service.py`, `report_service.py`, `net_worth_service.py`,
  `credit_service.py`, `reserve_fund_service.py`.
- Seeders: `seeders/transactions.py` (drop the hand-kept balance map and
  set `opening_balance` + directions instead).
- Views: `views/accounts.py`, `views/net_worth.py`,
  `views/dashboard_widgets/balance_card.py`,
  `views/reports_canned/net_worth_statement.py` (read derived values; no
  new strings expected, so run `i18n-verifier` only if a label changes).
- Backup/restore round-trip (`backup-full-schema-roundtrip`) must carry
  the renamed column.
- Tests: new `tests/unit/services/test_account_balances.py`,
  `tests/integration/test_account_balances.py`, e2e for
  `KAL-ACC-005`/`006`/`008` in `tests/e2e/test_accounts*.py` or the
  existing accounts e2e module.

## Open questions

- **Future-dated rows.** Does a transaction dated after today count
  toward "current" balance? Default: **yes, every row counts**, like the
  seeder did. `as_of` exists for callers that need a cut-off.
- **Unlinked legacy `transfer` rows** (mBank import before this change)
  have no recoverable direction. Default: backfill `out`. The anchored
  opening balance keeps today's figure right either way. Only a later
  edit of such a row could be off, and the user can fix it with
  `AccountUpdate.balance`. Record how many rows the migration touched in
  its log line.
- **Planned `transfer` posting.** `salary_service` creates a planned
  `transfer` with only the source account. If post-due writes a single
  leg today, default: it gets `out`, and the missing incoming leg goes in
  the chore inbox, not this plan.
- **Split transactions.** Default: the parent row's `amount` counts. The
  splits are a breakdown of the same money and are never summed on top.

## Implementation notes

- **Open questions, all taken at their defaults.**
  - Future-dated rows count toward the current balance; `as_of` cuts the
    ledger off for callers that need a date.
  - Unlinked legacy transfer legs are backfilled as `out`. The migration
    logs how many rows it touched.
  - A posted planned `transfer` gets `out`. The missing incoming leg is in
    the chore inbox.
  - Splits: only the parent row's `amount` counts (tested).
- **Enum storage.** Enums are stored by member *name* (`'TRANSFER'`,
  `'OUT'`), because no model sets `values_callable`. The CHECK constraint
  and the migration's SQL compare against names.
- **CHECK constraint.** `ck_transactions_transfer_direction`:
  `(type = 'TRANSFER') = (transfer_direction IS NOT NULL)`. It is the first
  CHECK constraint in the schema. It backs up the schema validator
  (`TransactionCreate`) and the service rule (`_settle_transfer_direction`),
  so a writer this plan missed fails loudly instead of skewing a balance.
- **Edit dialog turning a row into a transfer.** A row edited from expense or
  income into a transfer, without a direction given, keeps the way its money
  already went (expense → `out`, income → `in`), so the balance does not
  move. A transfer edited back into income/expense loses its direction.
- **`create_transfer` orients legs by position** and ignores the payloads'
  directions. `pair_as_transfer` sets them from the expense/income roles, not
  from id order.
- **`AccountResponse.balance` is required, with no default.** `AccountBase`
  used to give it `0.00`, which would have turned any forgotten ORM →
  response path into a silent zero. Responses are built with
  `AccountResponse.from_account(account, balance)`. The API routes no longer
  return ORM rows behind `type: ignore`.
- **Account edit dialog** gained a Balance field (KAL-ACC-008), prefilled
  with the current balance. It is sent only when changed, so saving a
  renamed account cannot pin the balance to a figure that went stale while
  the dialog was open (`AccountService.edited_balance`, unit-tested). New
  i18n key `accounts.balance_hint` (en + pl).
- **Existing tests.** Fixtures that built transfer legs without a direction
  now pass one: `out`, and `in` for the incoming leg of a pair.
  `Account(balance=…)` became `opening_balance=`. Nine tests in
  `test_net_worth_service.py` / `test_reserve_fund_service.py` meant "the
  account holds X today" and then wrote rows on that account. They now state
  X after writing the rows (`_settle_balance`, i.e. `AccountUpdate.balance`),
  with the same literals and assertions. `TestAccountServiceAdjustBalance`
  was deleted along with `adjust_balance`. The seeder-registry check now
  asserts opening balances are zero and derived balances are not.
- **Upgrade test runs on every backend.** It seeds its own SQLite file
  through `sqlite3`, so it carries no `_USE_POSTGRES` guard. `spec_coverage`
  only scans `tests/e2e` and `tests/integration`, so KAL-ACC-007 also has an
  API integration test.
- **Not exercised locally:** the migration and the CHECK constraint on
  PostgreSQL. The SQL is portable, but the Postgres CI job is the check.
- **Docs.** ADR-037 records the decision; `docs/architecture.md` links it.
  The existing chore about money flow's id-order guess now points at
  `transfer_direction`. A new chore covers the one-legged planned transfer.

## Implementation (filled by plan-archiver)
