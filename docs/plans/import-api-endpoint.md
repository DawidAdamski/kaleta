---
plan_id: import-api-endpoint
title: POST /api/v1/imports — import a bank statement through the API
area: api, import
effort: medium
status: draft
roadmap_ref: ../roadmap.md
---

# POST /api/v1/imports — import a bank statement through the API

![Import page vs REST API](../images/import-ui-vs-api.svg)

## Intent

This plan is the second half of the bug fix started in `import-pipeline-service`.
Kaleta 0.8.0 has no import endpoint. The only way to load statement rows
through the API is `POST /api/v1/transactions`, which stores one row exactly as
sent. That skips steps 1–8 in the image:

- no profile detection or parsing;
- no account match;
- no importer description format, so a later import will not see these rows
  as duplicates, because the duplicate check compares descriptions exactly;
- no transfer detection;
- no duplicate skip;
- no categorisation rules, even though `category_id` is required, so the
  client has to guess;
- no import run, so the file is missing from "Account coverage and recent imports".

On 2026-11-09, 5 rows loaded through the API matched the UI rows only because
the client copied the importer's logic by hand.

Depends on: `import-pipeline-service`.

## Scope

In scope:

1. **Route:** `POST /api/v1/imports`
   - **Raw body, not multipart.** The body is the statement file as
     `Content-Type: text/csv` or `application/octet-stream`. Options go in
     query parameters:
     - `filename` (required; used for rules and the import run),
     - `account_id`,
     - `default_expense_category_id` (required),
     - `default_income_category_id` (required),
     - `skip_duplicates` (default `true`),
     - `dry_run` (default `false`).

     Why not multipart: FastAPI parses form data **before** dependencies run,
     including the router's `require_api_auth`. An unauthenticated client could
     then upload any size, and Starlette spools files over 1 MB to temporary
     disk, so plain-text statements would land on disk.
   - **Read only after auth.** First reject on `Content-Length` greater than
     `settings.max_upload_bytes`. Then read `request.stream()` inside the route
     with a running byte count and stop with `413` when it passes the cap.
     Never write the body to disk.
   - **Row cap for the API:** `settings.api_import_max_rows` (default 5 000).
     Above it, return `413` with the row count. This bounds the per-row payee and
     duplicate queries in one request.
2. **Semantics**
   - `dry_run=true` returns `ImportPipeline.build` as JSON: the rows with final
     description, type, category, payee and a duplicate flag, the
     `new_payee_names`, the resolved account, and the transfer window. Nothing is
     written.
   - `dry_run=false` runs `build` and then `apply`, in one transaction.
3. **Idempotency**
   - An optional `Idempotency-Key` header is stored on the `ImportRun`. A repeat
     with the same key returns the first result with `200` and does not import
     again.
   - In addition, `ImportRun.file_hmac` stores a keyed HMAC of the body, keyed
     with a server secret so the digest does not reveal the content. The same
     file again for the same account returns `409` with the earlier run id,
     unless `allow_reimport=true`.
   - While importing, a PostgreSQL advisory lock is held per (family, account),
     so two concurrent requests cannot both pass the duplicate check.
   - Alembic migration: add `idempotency_key` and `file_hmac` (both nullable,
     with an index) to `import_run`.
4. **Responses** (Pydantic schemas in `src/kaleta/schemas/imports.py`):
   - `ImportRowPreview`: `date`, `amount`, `type`, `description`,
     `category_id`, `payee_name`, `duplicate: bool`.
   - `ImportDryRunResponse`: `account_id`, `profile`, `rows: list[ImportRowPreview]`,
     `new_payee_names`, `transfer_window: {date_from, date_to}`.
   - `ImportResponse`: `import_run_id`, `account_id`, `imported_count`,
     `skipped: list[{row_index, reason}]`, `transfer_window`.
   - Errors use the shared shape `{"error": {"code", "message"}}`:
     - `401`/`403` for auth;
     - `409` for an ambiguous account number or a duplicate file;
     - `413` when over the byte cap or the row cap;
     - `422` for readiness errors: no account, no categories, currency mismatch,
       a generic CSV without a saved mapping (the response lists the detected
       headers), or an unknown profile;
     - `423` when the data key is locked. A bearer import needs the token
       owner's key to be unlocked (`_bind_bearer_data_key`, `api/deps.py`).
       Document this in the endpoint description.
5. **Docs:** add `KAL-API-008` to `docs/bdd.md`, and state in the description of
   `POST /api/v1/transactions` that it does not apply rules or skip duplicates
   and that statements should use `/imports`.

Out of scope:

- Applying rules on plain `POST /api/v1/transactions`.
- An API for creating or editing categorisation rules.
- Transfer pair endpoints (`import-transfer-pairs-api`).
- Saving filename rules through the API.

## Acceptance criteria

- `uv run pytest tests/integration/test_api_imports.py -q`
- `uv run alembic upgrade head && uv run alembic check`
- `uv run lint-imports`
- `grep -c "KAL-API-008" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

Tests in `tests/integration/test_api_imports.py`:

- `test_import_mbank_statement_happy_path` asserts literal stored descriptions
  and categories.
- `test_dry_run_writes_nothing`.
- `test_same_file_twice_returns_409`; `test_idempotency_key_replays_result`.
- `test_unauthenticated_upload_rejected_before_body_read`.
- `test_body_over_cap_413`; `test_rows_over_cap_413`.
- `test_no_account_422`; `test_ambiguous_number_409`.
- `test_concurrent_imports_do_not_double_insert` (two tasks, one advisory lock).

## Touchpoints

- `src/kaleta/api/v1/imports.py` (new), `src/kaleta/api/v1/__init__.py`
- `src/kaleta/schemas/imports.py` (new)
- `src/kaleta/models/import_run.py` + an Alembic migration
- `src/kaleta/config/settings.py` — `api_import_max_rows`, the HMAC secret
  (reuse the existing app secret if one exists)
- `src/kaleta/services/import_pipeline.py` — `file_hmac`, the lock
- `tests/integration/test_api_imports.py`, `docs/bdd.md`

## Open questions

- Rate limiting: reuse the existing per-token limiter if there is one, or add a
  stricter one for `/imports`. Decide when implementing; it does not block the start.

## Implementation notes

## Implementation (filled by plan-archiver)
