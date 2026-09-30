---
adr_id: "037"
title: "Account Balances Derived from the Ledger"
status: accepted
---

# ADR-37: Account Balances Derived from the Ledger

- **Decision**: An account stores only `opening_balance`. Its current balance
  is `opening_balance` plus the signed sum of its transactions, computed on
  read by `AccountService.balances()` (one grouped query for every account).
  Every screen and service that shows a balance reads it there. Transfer legs
  carry `transfer_direction` (`out`/`in`), because `amount` is unsigned and a
  row typed `transfer` otherwise does not say which way the money went. A
  CHECK constraint (`ck_transactions_transfer_direction`) makes the direction
  present on every transfer leg and absent everywhere else.
- **Rationale**: The old `accounts.balance` was a number typed into the account
  form. Nothing in the ledger moved it, so the accounts list, the dashboard,
  net worth, the forecast, credit-card utilisation and reserve-fund progress
  all showed the figure from the last manual edit. A running column would need
  every write path to update it: manual add, edit, delete, bulk actions,
  import, pairing, posting planned occurrences, seeders and backup restore.
  One forgotten path would mean silent drift. A derived figure cannot drift,
  and the aggregate is cheap on SQLite and PostgreSQL alike.
- **Setting a balance by hand**: `AccountUpdate.balance` means "the current
  balance is X". The service moves `opening_balance` so that opening + ledger
  lands on X, and leaves every transaction as it is.
- **Upgrade**: migration `c4d5e6f7a8b9` backfills `transfer_direction` (a linked
  pair's lower id is `out`, an unlinked leg is `out`). It then sets
  `opening_balance = old balance − signed ledger`, so no user sees a different
  balance after upgrading, whatever the direction backfill guessed.
- **Rejected alternative**: a running `balance` column kept up to date by the
  services (`AccountService.adjust_balance` existed for that and was never
  called).
- **Plan**: [`accounts-ledger-balances`](../plans/archive/accounts-ledger-balances.md)
