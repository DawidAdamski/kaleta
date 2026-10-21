# Plan: Planned salary transfer posts both legs

status: in-progress
issue: (chore inbox — docs/plans/chores.md)
branch: fix/planned-salary-transfer-both-legs

## Problem

`SalaryService.create_salary_plan` ("Pay yourself a salary") builds a
`PlannedTransaction` of type `TRANSFER` on the **source** account and names
the target account only in the free-text description. When the occurrence is
posted (`PlannedTransactionService._ensure_posted`) a single outgoing leg is
written on the source account. Now that account balances follow the ledger
(`plan/accounts-ledger-balances`), the money leaves the source account and
arrives nowhere — net worth drops by the salary amount every month.

`NetWorthService._monthly_history` additionally filters its per-account
monthly delta to `INCOME`/`EXPENSE` non-internal rows, so it skips every
transfer row. The current-balance view (`AccountService.balances`, via
`signed_ledger_amount`) does count transfer legs, so history and the current
balance disagree about transfers.

## Investigation / decision gate

- The salary flow **already knows** the target account: the wizard
  (`views/wizard_salary.py`) collects both accounts into
  `SalaryPlanCreate.{from_account_id,to_account_id}` and
  `create_salary_plan` receives both. The target is simply not persisted
  structurally. **No view change is needed.**
- No API route consumes `PlannedTransactionCreate` (only views/services), so
  adding an optional field is not a REST contract change.
- Posting both legs is gated on `target_account_id is not None`, so
  **non-salary planned transfers keep their current single-leg behaviour**
  unchanged.

Conclusion: contained. Implementing.

## Changes

1. **Model** — `PlannedTransaction.target_account_id` (nullable FK →
   `accounts.id`, `ondelete=SET NULL`). The account the money arrives on, set
   only for salary self-transfers.
2. **Migration** — add the column + FK. `down_revision = e9ecbe7dd5b0`
   (current head). Reversible.
3. **Schema** — `PlannedTransactionCreate.target_account_id: int | None`
   (additive, defaults `None`).
4. **SalaryService.create_salary_plan** — set
   `target_account_id=payload.to_account_id`.
5. **PlannedTransactionService._ensure_posted** — when the plan is a transfer
   with a `target_account_id`, post **two linked legs** (OUT on the source,
   IN on the target, both `is_internal_transfer=True`, linked via
   `linked_transaction_id`). The OUT leg carries `planned_transaction_id`
   (so the `(planned_transaction_id, date)` unique key and the idempotency /
   `exclude_posted` checks keep working unchanged); the IN leg's
   `planned_transaction_id` is `NULL`. `create_transfer` itself commits and
   cannot run inside the savepoint-wrapped, idempotent posting path, so the
   two legs are built directly in the same linked shape it produces.
6. **NetWorthService._monthly_history** — roll each account's balance back
   using `signed_ledger_amount()` summed over **all** rows (income, expense
   and transfer legs signed by `transfer_direction`), matching exactly what
   `AccountService.balances` adds forward. History then reflects transfer
   legs consistently with the current balance; a properly-paired transfer
   nets to zero across accounts in every historical month.

## Tests

- Integration (`tests/integration/test_pay_yourself_salary.py`): post the
  salary planned transfer and assert money moves OUT of source and INTO
  target, and net-worth monthly history reflects it. `Covers: KAL-SAL-006`.
- Unit (`tests/unit/services/test_net_worth_service.py`): the two
  `TestInternalTransfersExcluded` tests encoded the old exclusion; rewritten
  to use properly-paired two-account transfers and assert the real invariant
  (net worth history unchanged by a transfer between own accounts).

## BDD

New scenario `KAL-SAL-006 @automated` under Feature "Pay Yourself a Salary":
posting the salary transfer moves money between the two accounts.

## Not in scope

- The non-salary single-leg planned-transfer posting path (unchanged).
- Any salary / planned-transaction view or form changes.
- The pre-existing FX caveat in `_monthly_history` (deltas not rate-converted).

## Implementation notes

- `target_account_id` FK uses `ondelete=SET NULL`: deleting the target
  account must not cascade-delete the salary plan; posting then falls back to
  the single-leg path.
- The two `TestInternalTransfersExcluded` unit tests previously asserted a
  lone outgoing transfer leg did **not** move history (300 / 1000-1000). With
  balances following the ledger that was inconsistent with the current
  balance; rewritten to paired transfers where net worth is genuinely flat.
