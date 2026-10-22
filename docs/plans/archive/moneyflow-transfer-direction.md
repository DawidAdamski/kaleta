---
plan_id: moneyflow-transfer-direction
title: Money Flow transfer direction from transfer_direction, not id order
area: reports (money flow)
effort: small
status: archived
archived_at: 2026-10-22
roadmap_ref: ../../roadmap.md
---

# Money Flow transfer direction from transfer_direction, not id order

## Intent
The Accounts-view Money Flow Sankey draws each internal transfer as an
account→account ribbon. `MoneyFlowService._net_transfers` picks the source
leg of a pair by id order (`src.id < dst.id`), assuming the lower-id leg is
the one the money left. Rows paired after the fact
(`TransactionService.pair_as_transfer`, the import "accept" flow) can have
the **incoming** leg older (lower id) than the outgoing one, so the ribbon is
drawn backwards — money appears to leave the destination account. The leg's
direction is now stored on the row (`Transaction.transfer_direction`,
`TransferDirection.OUT`/`IN`); read it instead of inferring from ids.

## Scope
- Only `MoneyFlowService._net_transfers`' leg-selection logic in
  `src/kaleta/services/money_flow_service.py`: pick the source leg by
  `transfer_direction == OUT` (destination is the `IN` leg) instead of by
  id order.
- Its tests (`tests/unit/services/test_money_flow_service.py`) and a new
  integration test reproducing the backwards case.
- The `KAL-FLW-*` Money Flow scenario in `docs/bdd.md`.
- **Not in scope:** `pair_as_transfer`, the import accept flow, account
  balances, budget-mode flow, or any other consumer of `transfer_direction`.

## Acceptance criteria
- `uv run pytest tests/unit/services/test_money_flow_service.py -q`
- `uv run pytest tests/integration/test_analysis_api.py -q`
- `grep -q "KAL-FLW-005" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/services/money_flow_service.py` (`_net_transfers`)
- `tests/unit/services/test_money_flow_service.py`
- `tests/integration/test_analysis_api.py`
- `docs/bdd.md` (Feature: Money Flow)

## Open questions
- Legacy / NULL `transfer_direction` rows — see Implementation notes.

## Implementation notes
- **NULL-direction fallback.** Migration
  `c4d5e6f7a8b9_ledger_derived_account_balances` backfilled every existing
  paired leg with the *same* id-order rule
  (`id < linked_transaction_id → OUT`) and added CheckConstraint
  `ck_transactions_transfer_direction` =
  `(type = 'TRANSFER') = (transfer_direction IS NOT NULL)`. So in any valid
  DB a transfer row always has a non-null direction, and for migration-era
  rows the stored direction already equals the old id-order verdict — the fix
  changes the drawing only for pairs created through the new
  `pair_as_transfer` path. The query still carries a deterministic fallback
  for defence in depth: when **both** legs' `transfer_direction` is NULL
  (which the constraint forbids), it keeps the old `src.id < dst.id`
  behaviour rather than dropping the pair from the flow. The fallback guards
  on *both* legs being NULL so an (impossible) mixed pair can never be
  double-counted or silently dropped.

## Implementation
- `c631f37` — fix(money-flow): draw transfer ribbons by transfer_direction,
  not id order. `_net_transfers` now selects the source leg by
  `transfer_direction == OUT` with the both-legs-NULL id-order fallback;
  adds BDD scenario KAL-FLW-005 @automated, an integration case in
  `tests/integration/test_analysis_api.py` (forces the incoming leg to the
  lower id via `pair_as_transfer`) and a unit case in
  `tests/unit/services/test_money_flow_service.py`.
