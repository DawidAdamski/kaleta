---
plan_id: import-transfer-pairs-api
title: Transfer pairs through the API, and validated links on PUT
area: api, transactions
effort: medium
status: draft
roadmap_ref: ../roadmap.md
---

# Transfer pairs through the API, and validated links on PUT

## Intent

After an import, the page lists "Suggested transfers": two rows on two of the
user's accounts with the same amount a few days apart. The user can accept a
pair (`ImportService.accept_transfer_pair`, which calls
`TransactionService.pair_as_transfer`) or dismiss it (`dismiss_transfer_pair`).
None of this is reachable through the API. The panel only appears on the import
page right after an import, inside that import's date window.

The real gap is wider than missing endpoints. `PUT /api/v1/transactions/{id}`
accepts `linked_transaction_id`, `type=transfer` and `transfer_direction` with
**no** checks. It skips `_validate_transfer_pair` (same currency, amounts within
tolerance, outgoing and incoming roles, not already linked), and it writes only
one side of the link. A client can link rows in different currencies, or leave a
half-linked pair.

On 2026-11-09 one pair (3 123,86 PLN, mKonto → savings, transactions 12568 and
12650) had a leg loaded through the API. It was linked with two hand-written
PUTs. The result was consistent only because the client was careful.

## Scope

In scope:

1. **Service home.** Move `suggest_transfer_pairs`, `accept_transfer_pair` and
   `dismiss_transfer_pair` from `ImportService` to `TransactionService`, next to
   `pair_as_transfer`. `ImportService` keeps thin delegates until callers move.
   Defaults: `DEFAULT_TRANSFER_PAIRING_DAYS = 3` and
   `DEFAULT_TRANSFER_AMOUNT_TOLERANCE = 0.01`, now in the service layer (see
   `import-pipeline-service`). Make the tolerance consistent: `pair_as_transfer`
   defaults to `0` today (`transaction_service.py:364`) and
   `accept_transfer_pair` to `0.01` (`import_service.py:2133`). Use one constant.
2. **Endpoints** (`src/kaleta/api/v1/transfer_pairs.py`):
   - `GET /api/v1/transfer-pairs/suggestions`:
     - `date_from` and `date_to` are **required**, with a maximum span of 92
       days (`422` above that);
     - `max_days_apart` defaults to 3 and must be between 1 and 14;
     - `amount_tolerance` defaults to 0.01;
     - returns `list[TransferPairSuggestionResponse]` with `outgoing`/`incoming`
       holding `{id, account_id, date, amount, description}`, plus `amount` and
       `currency`.
   - `POST /api/v1/transfer-pairs` takes `{transaction_ids: [a, b]}` in either
     order. The roles come from the types, as `pair_selected_as_transfer` does
     today. Returns `200` with both legs. If the two rows are already linked to
     each other it returns `200` without changing anything, so retries are safe.
   - `POST /api/v1/transfer-pairs/dismiss` takes `{transaction_ids: [a, b]}`. The
     ids are checked to exist first (`404`), so a foreign-key error can no longer
     surface as a `500`. Repeating the call is idempotent.
   - Errors: `404` for an unknown id (`NotFoundError`); `409` when a leg is
     already linked elsewhere (`ConflictError`); `422` for other validation
     errors (currency, amount, roles).
3. **Validated links on PUT.** When an update sets `linked_transaction_id`, or
   turns a linked row into a transfer, `TransactionService.update` runs
   `_validate_transfer_pair` and writes **both** sides in the same transaction.
   Clearing the link clears both sides. A client that sent valid pairs keeps
   working; one that sent invalid pairs now gets a `409` or `422`.
4. **Data check.** Add `scripts/check_transfer_links.py` (read-only). It lists
   transfers whose `linked_transaction_id` does not point back, and pairs with
   different amounts or currencies. Run it once on the self-hosted instance and
   record the result in "Implementation notes". The pair linked by hand on
   2026-11-09 was verified consistent through the API (both directions, same
   amount, opposite directions).

Out of scope:

- A "Suggested transfers" panel outside the import page, for example in
  Housekeeping. That is its own plan, with UI, i18n and e2e work.
- Unpairing, that is turning a transfer back into an expense and an income.
  Until it exists, the API docs must say that a wrong pair has to be fixed by
  editing both legs.
- Changing the suggestion algorithm.

## Acceptance criteria

- `uv run pytest tests/integration/test_api_transfer_pairs.py -q`
- `uv run pytest tests/unit/services/test_transfer_pairing.py tests/integration/test_transfer_pairing.py -q`
- `uv run pytest tests/integration -q -k "put_link_validates or put_link_writes_both_sides"`
- `uv run python scripts/check_transfer_links.py --help`
- `grep -c "KAL-API-009" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

Tests in `tests/integration/test_api_transfer_pairs.py`:

- `test_suggest_requires_date_range`, `test_suggest_span_capped`
- `test_accept_links_both_legs` (checks `type=transfer`, no category, links in
  both directions)
- `test_accept_is_idempotent`, `test_accept_unordered_ids`
- `test_accept_different_currency_422`, `test_accept_already_linked_409`,
  `test_accept_unknown_id_404`
- `test_dismiss_unknown_id_404`, `test_dismissed_pair_not_suggested`
- In the PUT tests file: `test_put_link_validates`, `test_put_link_writes_both_sides`.

## Touchpoints

- `src/kaleta/services/transaction_service.py`: moved methods, the `update`
  link handling, one tolerance constant
- `src/kaleta/services/import_service.py`: delegates
- `src/kaleta/api/v1/transfer_pairs.py` (new), `src/kaleta/api/v1/__init__.py`
- `src/kaleta/schemas/`: suggestion and pair schemas
- `scripts/check_transfer_links.py` (new)
- `docs/bdd.md`: `KAL-API-009`; API docs

## Open questions

None blocking.

## Implementation notes

## Implementation (filled by plan-archiver)
