---
plan_id: import-transfer-pairs-api
title: Transfer pairs through the API, and validated links on PUT
area: api, transactions
effort: medium
status: in-progress
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

- Suggest: `test_suggest_requires_date_range`, `test_suggest_span_capped`
- Accept: `test_accept_links_both_legs` (checks `type=transfer`, no category,
  links in both directions)
- Accept: `test_accept_is_idempotent`, `test_accept_unordered_ids`
- Accept errors: `test_accept_different_currency_422`,
  `test_accept_already_linked_409`, `test_accept_unknown_id_404`
- Dismiss: `test_dismiss_unknown_id_404`, `test_dismissed_pair_not_suggested`
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

- **Service home.** `suggest_transfer_pairs`, `accept_transfer_pair`,
  `dismiss_transfer_pair` and the `TransferPairSuggestion` dataclass now live in
  `transaction_service.py`; `ImportService` keeps one-line delegates (the import
  page still calls them) and `detect_and_link_transfers`. The dataclass gained
  `outgoing_account_id`/`incoming_account_id` and per-leg amounts for the API
  response. The two views that typed against `import_service.TransferPairSuggestion`
  import it from `transaction_service` (mypy's no-implicit-reexport); that is
  the only view change, plus `views/settings/constants.py` re-exporting the two
  defaults instead of defining them.
- **One tolerance.** `DEFAULT_TRANSFER_AMOUNT_TOLERANCE = 0.01` and
  `DEFAULT_TRANSFER_PAIRING_DAYS = 3` are defined once, in `transaction_service`.
  `pair_as_transfer` defaulted to `0`; it now uses the constant, so the ledger's
  "Mark as transfer" accepts a one-grosz difference like the import review does.
- **Already linked to each other is not a conflict.** `_validate_transfer_pair`
  refuses a leg linked to a *third* row, not one linked to its partner. That is
  what lets the second hand-written PUT of the 2026-11-09 fix (B → A after A → B)
  succeed, and a half link (A → B, B → nothing) be completed.
- **Idempotent accept.** `pair_selected_as_transfer` returns the legs unchanged
  when the rows already link to each other, oriented by their stored
  `transfer_direction`. Without that, re-pairing two import-typed transfer legs
  would fall back to "lower id goes out" and could flip the directions; a unit
  test pins it (`test_pairing_a_linked_pair_again_changes_nothing`).
- **PUT semantics** (`TransactionService._apply_link_update`, after all other
  fields are applied so the checks see the row as saved):
  - a new partner is a pairing: same checks as `pair_as_transfer`, and both legs
    become `type=transfer`, internal, without category, with directions. A leg
    that already says `transfer_direction` decides the roles; two legs saying
    the same direction are a `422`. Otherwise the types decide, as in
    `orient_transfer_legs`. Linking to itself is a `422`, to an unknown id a `404`;
  - `linked_transaction_id: null` clears the partner's link back as well; both
    rows keep `type=transfer` (unpairing is out of scope, as the API docs say);
  - a linked row edited into a transfer re-validates the pair and writes both legs;
  - a PUT that moves the row to another account *and* links it reads the new
    account's currency (`errors.transaction.account_not_found`, new i18n key in
    `en.json`/`pl.json`, if that account is gone).
- **No autoflush while checking a PUT link.** The checks run with the update's
  fields already on the row, and the partner lookup used to autoflush them: a
  PUT moving the row to a missing account *and* linking it surfaced as a
  foreign-key error (a `500`) instead of `account_not_found`.
  `_link_by_update` now runs its lookups under `session.no_autoflush`; found by
  `test_link_moved_to_a_missing_account_is_not_found`, added after the critic
  noted the branch had no test.
- **Endpoints.** `GET /suggestions` refuses `date_to < date_from` as well as a
  span over 92 days (both `422`, raised in the route: they are request-shape
  rules, not domain rules). `max_days_apart` is `1..14`, `amount_tolerance >= 0`.
  `POST /transfer-pairs` returns `{outgoing, incoming}` as full
  `TransactionResponse`s; `POST /dismiss` returns `204`. Two equal ids are a `422`.
- **Data check.** `scripts/check_transfer_links.py` reads through the API of a
  running instance (`--url`, `--token`/`KALETA_API_TOKEN`), GET only, so it needs
  neither database credentials nor the family-schema plumbing, and checks the
  data exactly the way the 2026-11-09 pair was checked. It reports `one_sided`,
  `dangling`, `amount_mismatch`, `currency_mismatch` and `same_direction` links;
  exit code 1 when anything is found. Tests feed it real API responses
  (`tests/integration/test_check_transfer_links.py`).
- **Acceptance list format.** The DoD gate runs every acceptance bullet that
  starts with a backtick as a shell command, so the bullets naming the tests in
  `test_api_transfer_pairs.py` were read as commands (`command not found`). They
  now start with a word ("Suggest:", "Accept:", …); the names and the tests are
  unchanged and all run under the first criterion.
- **Not run here: the self-hosted check.** This session has no URL or token for
  the self-hosted instance, so the one-off run is left to the owner:
  `KALETA_API_TOKEN=… uv run python scripts/check_transfer_links.py --url <instance>`.
  The result goes in this section before the plan is archived.

## Implementation (filled by plan-archiver)
