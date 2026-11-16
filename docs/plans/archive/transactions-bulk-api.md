---
plan_id: transactions-bulk-api
title: Transactions REST API — bulk create, bulk recategorise, new transfer, ledger CSV
area: api, transactions
effort: medium
status: archived
archived_at: 2026-11-16
roadmap_ref: ../../roadmap.md
---

# Transactions REST API — bulk create, bulk recategorise, new transfer, ledger CSV

## Intent
An API client (a script, Claude) that cleans up a ledger works one row at a time:
`/api/v1/transactions` has list/create/get/update/delete only. Four things the UI
can do have no API route, although `TransactionService` already does them:

- `set_category_bulk`: the ledger multi-select "change category"
  (`views/transactions/bulk_category_dialog.py`);
- `create_transfer`: the add dialog's two-legged transfer, cross-currency included
  (`views/transactions/add_dialog.py`);
- `export_ledger_csv` / `ledger_csv_filename`: Settings → Data → ledger CSV
  (`views/settings/data_tab.py`, KAL-SET-020);
- `create_bulk`: many simple rows in one commit (today used only by
  `ImportPipeline.apply`).

Expose them, all-or-nothing, with a server-side cap on how many rows or ids one
request may carry, following the `POST /api/v1/imports` cap pattern
(`settings.api_import_max_rows` → `PayloadTooLargeError` → `413`).

**Not a duplicate of transfer pairing.** `/api/v1/transfer-pairs` (KAL-API-009,
merged in #425) pairs two rows that *already exist*, and refuses rows in two
currencies. A new transfer through the API today takes three non-atomic calls
(`POST /transactions` twice, then `POST /transfer-pairs`), can leave a lone leg
behind when the second call fails, and cannot be cross-currency at all. The new
`POST /transactions/transfers` creates both legs in one commit.

## Scope

### Routes (all in `src/kaleta/api/v1/transactions.py`, all on `get_session`)
Declare every fixed-path route **before** `GET /{transaction_id}`: FastAPI tries
routes in order, and `/export` would otherwise hit `{transaction_id}` and fail the
int parse with `422` instead of falling through.

- `POST /transactions/bulk` — body `TransactionBulkCreate`
  (`transactions: list[TransactionCreate]`, `min_length=1`) → `201`
  `TransactionBulkCreateResponse` (`created_count: int`, `ids: list[int]`, ids in
  request order). One commit; any refused row refuses the whole request.
- `POST /transactions/bulk/category` — body `TransactionBulkCategory`
  (`transaction_ids: list[int]`, `min_length=1`; `category_id: int`) → `200`
  `TransactionBulkCategoryResponse` (`updated_count: int`).
- `POST /transactions/transfers` — body `TransferCreate` (new, see below) → `201`
  `TransferPairResponse` (reuse `kaleta.schemas.transfer_pair.TransferPairResponse`:
  `outgoing` / `incoming` `TransactionResponse`, exactly what `create_transfer`
  returns as a tuple).
- `GET /transactions/export` → `200`, `media_type="text/csv; charset=utf-8"`,
  header `Content-Disposition: attachment; filename="<ledger_csv_filename()>"`.
  The body is `export_ledger_csv()`'s bytes in a plain `Response` (see Open
  questions on streaming).
- Each operation has a `summary` and a `description` naming its limits and its
  all-or-nothing behaviour, in the style of the existing routes.

### Schemas (`src/kaleta/schemas/transaction.py`)
Service returns that need a response schema: `create_bulk` returns a bare `int`
(no ids), `set_category_bulk` a bare `int`, `create_transfer` a
`tuple[Transaction, Transaction]` of ORM rows, `export_ledger_csv` `bytes`.

- `TransactionBulkCreate`, `TransactionBulkCreateResponse`,
  `TransactionBulkCategory`, `TransactionBulkCategoryResponse` (new).
- `TransferCreate` (new): `from_account_id: int`, `to_account_id: int`,
  `amount: Decimal` (`decimal_places=2`, `gt=0`), `date: datetime.date`,
  `description: str` (`max_length=500`, default `""`), `notes: Notes`,
  `exchange_rate: Decimal | None` (`gt=0`), `to_amount: Decimal | None`
  (`decimal_places=2`, `gt=0`). Shape checks only; everything that needs the
  database lives in the service.

### Service (`src/kaleta/services/transaction_service.py`) — new validation needed
Validation belongs here, not in the routes. What each existing method lacks:

- **`create_bulk` has no checks at all.** It drops `splits`, `tag_ids` and
  `payee_name` silently, never checks that `account_id` / `category_id` /
  `payee_id` exist (an unknown `account_id` becomes an `IntegrityError` at commit,
  which `statement_error_handler` turns into a `500`), returns no ids, and stores a
  `type=transfer` row as a lone leg. Leave `create_bulk` unchanged (the import
  pipeline relies on its speed and `commit=False`) and add a new method
  **`create_many(creates: list[TransactionCreate]) -> list[int]`** that:
  1. refuses more rows than `settings.api_bulk_max_items` with
     `PayloadTooLargeError` (`413`), message naming the count and the cap;
  2. refuses, with `ValidationError` naming the row index (0-based) — `422`:
     a row with `splits`, `tag_ids`, `payee_name` or `linked_transaction_id`
     ("not supported in bulk; use POST /api/v1/transactions"), and a row with
     `type=transfer` ("use POST /api/v1/transactions/transfers");
  3. checks in one `select … where id in (…)` each that every `account_id`,
     `category_id` and `payee_id` exists → `ValidationError` naming the missing
     ids (`422`, codes `unknown_account`, `unknown_category`, `unknown_payee`);
  4. checks each row's category type matches the row type (income ↔ income,
     expense ↔ expense), the same rule `set_category_bulk` applies →
     `ValidationError` (`422`);
  5. then builds the rows the way `create_bulk` does, `flush`es, reads the ids,
     commits once and returns the ids in input order. Nothing is written when any
     check fails.
- **`set_category_bulk` skips unknown ids silently** (it returns how many it
  found). For all-or-nothing, change it to: de-duplicate the ids; refuse more than
  `settings.api_bulk_max_items` (`PayloadTooLargeError`); after the select, raise
  `NotFoundError` listing the missing ids (`404`) before changing anything. Its
  other checks (category exists → `404`, income/expense only → `422`, no split rows
  → `422`, type match → `422`) stay. The UI dialog only sends ids it just listed,
  so the stricter rule only shows there when a row was deleted meanwhile; it
  already catches `KaletaError`. Keep its existing unit tests green
  (`tests/unit/services/test_transaction_service.py`, around `set_category_bulk`).
- **`create_transfer` checks nothing** (same account, missing account, currency,
  amounts). Leave it as the low-level writer (the add dialog and
  `ReserveFundService._move` call it) and add
  **`create_transfer_between(data: TransferCreate) -> tuple[Transaction, Transaction]`**
  that:
  1. loads both accounts (`session.get(Account, …)`) → `NotFoundError` (`404`)
     when either is missing;
  2. refuses `from_account_id == to_account_id` → `ValidationError` (`422`), reuse
     `message_key="errors.transaction.transfer_different_accounts"`;
  3. same currency: refuses `exchange_rate` or a `to_amount` that differs from
     `amount` (`422`); the incoming leg's amount is `amount`;
  4. different currencies: requires `exchange_rate` (`422` without it); the
     incoming amount is `to_amount` when given, else
     `(amount * exchange_rate).quantize(Decimal("0.01"), ROUND_HALF_UP)` — the add
     dialog's rule (`dest_amt = amount * rate`), with the rounding made explicit;
  5. builds both `TransactionCreate` legs exactly as `add_dialog.py` does
     (`type=TRANSFER`, `transfer_direction` OUT / IN, `is_internal_transfer=True`,
     same `date`, `description`, `notes`, `exchange_rate` on both, no category),
     calls `create_transfer(outgoing, incoming)`, then for a cross-currency
     transfer `CurrencyRateService(self.session).record_transfer_rate(date,
     from_currency, to_currency, exchange_rate)` — the add dialog does the same.
- **`export_ledger_csv`** needs nothing: the route only wraps its bytes.

### Settings (`src/kaleta/config/settings.py`)
- `api_bulk_max_items: int = 1000` (`KALETA_API_BULK_MAX_ITEMS`), with a
  `field_validator` refusing `< 1`, next to `api_import_max_rows`. One cap for both
  rows of `POST /bulk` and ids of `POST /bulk/category`. Document it where
  `KALETA_API_IMPORT_MAX_ROWS` is documented (`docs/tech-stack.md` env table).

### Scenario (paste into `docs/bdd.md`, Feature: REST API, after KAL-API-009)

```gherkin
  KAL-API-014 @automated
  Scenario: Bulk transaction operations through the API
    Given a valid API bearer token
    And PLN accounts "mKonto" and "Savings", and an EUR account "Revolut EUR"
    And expense categories "Spożywcze" and "Transport", and an income category "Wynagrodzenie"
    When I POST to /api/v1/transactions/bulk an expense of 45.99 on "mKonto" dated 2026-11-03 described "LIDL WARSZAWA" and an expense of 120.00 on "mKonto" dated 2026-11-04 described "ORLEN", both in "Spożywcze"
    Then the response is 201 with created_count 2 and two ids
    And a bulk request with a row on an account that does not exist is 422 and stores none of its rows
    And a bulk row carrying splits, tag_ids or type transfer is 422
    When I POST both ids and "Transport" to /api/v1/transactions/bulk/category
    Then the response is 200 with updated_count 2 and both rows are in "Transport"
    And the same request with "Wynagrodzenie" is 422 and neither row changes
    And the same request with one id that does not exist is 404 and neither row changes
    And more rows or ids than KALETA_API_BULK_MAX_ITEMS is 413
    When I POST a transfer of 500.00 from "mKonto" to "Savings" dated 2026-11-05 described "Na oszczędności" to /api/v1/transactions/transfers
    Then the response is 201 with an outgoing leg on "mKonto" and an incoming leg on "Savings", both 500.00, type transfer, internal, linked to each other
    And a transfer from "mKonto" to "mKonto" is 422, and one to an account that does not exist is 404
    And a transfer from "mKonto" to "Revolut EUR" without an exchange_rate is 422
    And a transfer of 460.00 from "mKonto" to "Revolut EUR" with exchange_rate 0.2350 stores an incoming leg of 108.10
    When I GET /api/v1/transactions/export
    Then the response is 200 text/csv with Content-Disposition attachment and a filename like "kaleta_ledger_2026-11-15.csv"
    And the first line is "date,type,amount,currency,account,category,payee,description,tags,is_internal_transfer"
    And a line is "2026-11-03,expense,45.99,PLN,mKonto,Transport,,LIDL WARSZAWA,,false"
```

### Out of scope
- Transfer **pairing** of existing rows, suggestions, dismissals, unpairing:
  `/api/v1/transfer-pairs` (KAL-API-009) already does it.
- Bulk update of other fields (date, payee, tags, account) and bulk delete.
- Splits and tags in bulk create (refused with `422`; one row at a time through
  `POST /api/v1/transactions`). Categorisation rules, duplicate skipping and import
  runs: that is `POST /api/v1/imports`.
- Filters on the CSV export (date range, account) and other export formats; a
  streaming rewrite of `export_ledger_csv` (see Open questions).
- Changing `create_bulk` or `create_transfer` themselves, or the UI views that call
  them.
- An `Idempotency-Key` on the bulk routes.
- Validating `linked_transaction_id` on single `POST /api/v1/transactions`
  (it is stored on one side only): if worth fixing, a line in
  `docs/plans/chores.md`, not here.

## Acceptance criteria
- `uv run pytest tests/integration/test_api_transactions_bulk.py -q`
- Tests: `test_bulk_create_stores_both_rows_and_returns_ids` (201, created_count 2,
  ids resolve with GET to 45.99 / 120.00 on mKonto), `test_bulk_create_unknown_account_stores_nothing`
  (422, transaction count unchanged), `test_bulk_create_refuses_splits_tags_and_transfer_rows`,
  `test_bulk_category_moves_both_rows`, `test_bulk_category_wrong_type_changes_nothing`,
  `test_bulk_category_unknown_id_is_404_and_changes_nothing`,
  `test_bulk_over_cap_is_413` (monkeypatch `settings.api_bulk_max_items` to 1; both
  routes), `test_transfer_creates_two_linked_legs`,
  `test_transfer_same_account_is_422_unknown_account_404`,
  `test_cross_currency_transfer_needs_rate_and_rounds_incoming_leg` (108.10),
  `test_export_is_csv_attachment_with_scenario_row`, and
  `test_openapi_gives_every_bulk_operation_a_summary` (asserted on `app.openapi()`).
  The module docstring carries `Covers: KAL-API-014`; expected values are the
  scenario's literals, never computed by calling the service.
- Unit tests for the new service rules sit in
  `tests/unit/services/test_transaction_service.py` (create_many checks,
  set_category_bulk unknown-id `NotFoundError`, create_transfer_between rounding).
- `uv run pytest tests/unit/services/test_transaction_service.py -q`
- `uv run pytest tests/integration/test_ledger_csv_export.py -q`
- `uv run pytest tests/integration/test_api_transfer_pairs.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `grep -c "KAL-API-014" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

## Touchpoints
- `src/kaleta/api/v1/transactions.py` — four routes, before `GET /{transaction_id}`
- `src/kaleta/services/transaction_service.py` — new `create_many`,
  `create_transfer_between`; stricter `set_category_bulk`
- `src/kaleta/services/currency_rate_service.py` — read only
  (`record_transfer_rate`)
- `src/kaleta/schemas/transaction.py` — `TransactionBulkCreate`,
  `TransactionBulkCreateResponse`, `TransactionBulkCategory`,
  `TransactionBulkCategoryResponse`, `TransferCreate`
- `src/kaleta/schemas/transfer_pair.py` — read only (`TransferPairResponse` reused)
- `src/kaleta/config/settings.py` — `api_bulk_max_items` + validator
- `src/kaleta/exceptions.py` — read only (`PayloadTooLargeError` → 413,
  `NotFoundError` → 404, `ValidationError` → 422)
- `src/kaleta/views/transactions/bulk_category_dialog.py` — read only; check its
  error path still toasts on the new `NotFoundError`
- `tests/integration/test_api_transactions_bulk.py` (new),
  `tests/unit/services/test_transaction_service.py`
- `docs/bdd.md` (KAL-API-014), `docs/tech-stack.md` (`KALETA_API_BULK_MAX_ITEMS`)

## Open questions
- **Stream the CSV?** `export_ledger_csv` loads every row and returns one `bytes`.
  Default: no. Wrap the bytes in a plain `Response` with `Content-Disposition`; a
  household ledger is a few MB at most. Record the measured size of the test
  ledger's export only if it surprises.
- **Cap value and one setting or two?** Default: one setting,
  `KALETA_API_BULK_MAX_ITEMS=1000`, for rows and ids alike. `413`, as imports.
- **Cap the ids by schema (`max_length`, `422`) or service (`413`)?** Default:
  service, `413`, so the limit follows the setting and matches imports.
- **Should `set_category_bulk`'s new unknown-id check also apply to the UI?**
  Default: yes. The service is shared, and a silent partial update is the thing the
  method's own docstring promises never to do.
- **Path names.** Default: `POST /transactions/bulk`, `POST /transactions/bulk/category`,
  `POST /transactions/transfers`, `GET /transactions/export`.
- **Cross-currency rate recorded in the same commit?** `create_transfer` commits,
  and `CurrencyRateService.create` writes afterwards, as in the add dialog.
  Default: keep that order (parity with the UI); do not refactor `create_transfer`'s
  commit. Note it in Implementation notes if a rate write can fail after the legs
  are stored.
- **Bulk rows with `planned_transaction_id`?** Default: allowed, but `create_many`
  checks the id exists the same way it checks `account_id`
  (`unknown_planned_transaction`, `422`). An unknown id would otherwise hit the same
  FK `IntegrityError` → `500`.
- **Filename date in the test.** `ledger_csv_filename()` uses `date.today()`.
  Default: the test matches `kaleta_ledger_\d{4}-\d{2}-\d{2}\.csv`. The scenario's
  "2026-11-15" is only an example.

## Implementation notes
- **Scenario id:** KAL-API-014, after KAL-API-012 in `docs/bdd.md` (013 is on the open reserve-funds branch).
- **Paths:** the plan defaults — `POST /transactions/bulk`, `POST /transactions/bulk/category`,
  `POST /transactions/transfers`, `GET /transactions/export`, all declared before
  `GET /{transaction_id}`.
- **`create_many`** is new; `create_bulk` is untouched (the import pipeline keeps its fast,
  trusting path). Refusals: a row with splits / tag_ids / payee_name / linked_transaction_id
  or a transfer row → 422 `unsupported_in_bulk` naming the 0-based row; unknown account,
  category, payee or planned transaction → 422 `unknown_account` / `unknown_category` /
  `unknown_payee` / `unknown_planned_transaction` (one `IN` query per kind); a category of the
  other type → 422 `category_type_mismatch`. Ids come from one `flush` before the single commit.
  The category types are read by loading `Category` rows: a `select(Category.id,
  Category.type).tuples()` raised `TypeError: 'ChunkedIteratorResult' object is not
  subscriptable` in this session setup, so the method avoids the column-tuple form.
- **Cap:** one setting, `api_bulk_max_items` (`KALETA_API_BULK_MAX_ITEMS`, default 1000,
  validator `>= 1`), checked in the service → `PayloadTooLargeError` (413) for rows and for
  de-duplicated ids alike. Documented in `docs/tech-stack.md` next to the other API settings
  (`KALETA_API_IMPORT_MAX_ROWS` is not in that table, so there was no row to sit beside).
- **`set_category_bulk`** now de-duplicates the ids, applies the cap, and raises
  `NotFoundError` listing missing ids before changing anything. The ledger dialog
  (`bulk_category_dialog.py`) already catches `KaletaError` and toasts, so the stricter rule
  only shows when a selected row was deleted meanwhile. Existing unit tests stay green; a new
  one covers the unknown id.
- **`create_transfer_between`** is new; `create_transfer` is untouched. Unknown account → 404,
  same account → 422 (`errors.transaction.transfer_different_accounts`), same currency with a
  rate or a different `to_amount` → 422, two currencies without a rate → 422. The incoming leg is
  `to_amount`, else `amount × rate` quantized `ROUND_HALF_UP` (unit-tested with 2.345 → 2.35).
- **Rate recording order:** as in the add dialog, `create_transfer` commits the legs and
  `record_transfer_rate` writes afterwards. If the rate write failed, the legs would stay
  stored without a recorded rate — the same as the UI today; not refactored.
- **CSV:** not streamed; the route wraps `export_ledger_csv()`'s bytes in a `Response` with
  `text/csv; charset=utf-8` and `Content-Disposition: attachment; filename="…"`. The test
  matches the filename by pattern since it carries today's date.

## Implementation

Landed on 2026-11-16 (PR #435).

| SHA | Author | Date | Message |
|---|---|---|---|
| `d2ee7362` | Dawid Adamski | 2026-11-16 | Merge pull request #435 from DawidAdamski/plan/transactions-bulk-api |

**Files changed:**
- docs/bdd.md
- docs/plans/transactions-bulk-api.md
- docs/tech-stack.md
- src/kaleta/api/v1/transactions.py
- src/kaleta/config/settings.py
- src/kaleta/schemas/transaction.py
- src/kaleta/services/transaction_service.py
- tests/integration/test_api_transactions_bulk.py
- tests/unit/services/test_transaction_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
