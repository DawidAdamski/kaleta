# Ledger: sign a transfer leg by its direction

status: in-progress
issue: (chore, docs/plans/chores.md ~line 344)

## Intent
The ledger shows every transfer leg as money out. `TransactionService.signed_amount`
signs by transaction *type* only, so the INCOMING leg of a transfer (e.g. a goal
contribution arriving on the destination account) reads `-500.00` on the account it
arrived on, instead of `+500.00`. Transfer rows now carry `transfer_direction`
(`Transaction.transfer_direction`, enum `TransferDirection{OUT, IN}`). Sign a transfer
leg by its direction: incoming -> positive, outgoing -> negative. Non-transfer rows keep
their existing type-based sign.

## Scope
- `TransactionService.signed_amount` — add a `transfer_direction` parameter and branch on
  it for transfer legs.
- `TransactionService.format_signed_amount` — thread the direction through.
- `TransactionService.build_table_row` — the ledger's row builder; pass the row's
  `transfer_direction` into the two helpers so ledger rows carry the right sign.
- Its direct tests (unit + a new integration test) and the matching BDD scenario.

## Not in scope
- Dashboard "recent transactions" widget, planned-occurrence rows, forecast rows and the
  `views/components/amount_label.py` wrappers. They still call the 2-arg form; the default
  keeps their current behaviour. The reported bug is the **ledger**; widening to those
  surfaces would break the single-purpose diff. (Could be a follow-up chore.)
- Account balances / flow readers: `AccountService.signed_ledger_amount` already signs by
  direction in SQL and is untouched.
- `net_of_rows`: it excludes transfer rows by type entirely, so the sign of a transfer
  leg's `amount_value` does not reach it. Logic unchanged.

## Acceptance
- `signed_amount(amount, TRANSFER, TransferDirection.IN)` is positive; with `OUT` negative.
- A transfer's incoming leg's `build_table_row` `amount_value` is positive on the
  destination account; the outgoing leg's is negative on the source. (integration test,
  BDD literals)
- Non-transfer rows unchanged; income positive, expense negative.
- `uv run ruff check . && ruff format --check . && mypy src/ && lint-imports` green.
- `uv run python scripts/spec_coverage.py` green.

## Touchpoints
- src/kaleta/services/transaction_service.py (signed_amount, format_signed_amount,
  build_table_row, net_of_rows docstring)
- tests/integration/test_transfer_pairing.py (new test)
- tests/unit/services/test_transaction_service.py (extend signed_amount unit coverage)
- docs/bdd.md (new KAL-TRF-005 scenario)

## Implementation notes
- Fix: `signed_amount` gained an optional `transfer_direction` parameter. Income -> +abs;
  a transfer leg with `TransferDirection.IN` -> +abs; everything else (expense, transfer
  OUT, transfer with no direction) -> -abs. `format_signed_amount` threads the direction
  through. `build_table_row` now passes `transaction.transfer_direction` into both helpers
  so ledger rows (and the `amount_value` a selection total sums) carry the right sign.
- No existing test had to be re-literalled. The one existing unit assertion for a transfer
  (`test_signed_amount_is_positive_only_for_income`, `signed_amount(1500, TRANSFER)` == -1500)
  calls the 2-arg form with no direction, which still falls back to money out — so it stays
  correct and green, now documented as the no-direction fallback. The `build_table_row`
  transfer assertions in `test_transfer_pairing.py::...is_out_of_month_totals_and_neutral`
  only check `type`/colour, not the amount sign, so they were unaffected.
- `net_of_rows` is unaffected: it filters transfers out by `type` before summing, so the
  per-leg sign never reaches it (KAL-TXN-015 and its unit tests stay green). Its docstring
  stated the old rationale ("the ledger ... paints both as outflows", "no direction"),
  which my change falsifies; rewrote that clause to the true reason (money only moved
  between the user's own accounts, so the net stays silent) and noted the per-leg sign now
  lives in `signed_amount`. Logic unchanged — docstring-only edit in the function family I
  touched.
- Full fast tier green: 3389 passed. Static gates (ruff/format/mypy/lint-imports) and
  spec_coverage all green. No ripple beyond `signed_amount` + `build_table_row`.
