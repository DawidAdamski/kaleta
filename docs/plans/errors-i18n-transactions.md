---
plan_id: errors-i18n-transactions
title: Localize transaction_service error toasts
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize transaction_service error toasts

## Intent
A follow-up slice of [`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md),
which shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort
(payee identity / merge-undo). This slice migrates **only**
`src/kaleta/services/transaction_service.py`: its user-facing `KaletaError`
raises now carry an `errors.transaction.*` key so a Polish session reads the
toast in Polish, while logs, event capture and the API keep reading the
English `exc.message`.

## Scope
Covers:
- `transaction_service.py`: add `message_key="errors.transaction.<slug>"`
  (+ `params` where the message interpolates) to each user-facing raise,
  keeping the existing English string as the positional `message` fallback.
- `src/kaleta/exceptions.py`: thread `message_key`/`params` through
  `StaleWriteError.__init__` (it already takes a `changed_by` kwarg) so the
  stale-write toast can localize. Minimal hook; no behaviour change.
- The `errors.transaction` block in `en.json` and `pl.json` (22 keys).
- `docs/bdd.md`: `KAL-ERR-002` + a covering integration test.

Does NOT cover:
- Any other service (each gets its own follow-up slice — the chore line
  stays open until all services are done).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still emits the English `message`).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-002" docs/bdd.md`
- `uv run pytest tests/integration -k "error_i18n" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/transaction_service.py` — migrated raises.
- `src/kaleta/exceptions.py` — `StaleWriteError` carries key/params.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.transaction.*`.
- `docs/bdd.md` — `KAL-ERR-002`; `tests/integration/test_error_i18n_transactions.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes
- **Slice boundary.** This covers `transaction_service` only; the parent
  plan's "remaining services get their own follow-up slices" is honoured.
  `chores.md` follow-up line stays unticked.
- **Migrated raises (22 keys over 22 raise statements):**
  - `pair_as_transfer` — `transfer_needs_two_rows`; `not_found_id`
    (`{transaction_id}`) for both the expense-leg and income-leg
    "not found" raises.
  - `pair_selected_as_transfer` — `not_found`, `transfer_needs_both_directions`.
  - `set_category_bulk` — `category_not_found` (`{category_id}`),
    `only_income_expense_categories`, `split_category_per_line`,
    `category_type_mismatch` (`{category_type}`).
  - `_validate_transfer_pair` — `outgoing_leg_not_income`,
    `incoming_leg_not_expense`, `transfer_different_accounts`,
    `transfer_currency_mismatch`, `transfer_amount_mismatch`,
    `already_linked` (`{transaction_id}`), `split_cannot_be_transfer`.
  - `_validate_split_sum` — `split_needs_at_least_one`,
    `split_sum_mismatch` (`{amount}`, `{remaining}`).
  - `update` — `split_amount_needs_splits`, `type_requires_category`
    (`{transaction_type}`).
  - `_refuse_stale_write` — `stale_write_by_member` (`{changed_by}`),
    `stale_write_elsewhere`. The `changed_by` kwarg still threads through
    (`StaleWriteError.__init__` now forwards `message_key`/`params` to
    `KaletaError`).
  - `_settle_transfer_direction` — `transfer_leg_needs_direction`.
- **Skipped raises (kept English, no key) — and why:**
  - `create` `KaletaError("Transaction id=… not found after commit")`,
    `create_transfer` / `pair_as_transfer` `KaletaError("Transfer legs not
    found after commit")` — pure post-commit invariants. They cannot be
    reached by a user action (the row was just committed); a base
    `KaletaError` here is developer-facing, never a toast. These three are
    the only skipped raises.
  - **Correction (reviewer).** The `pair_as_transfer`
    `NotFoundError(f"Transaction {expense_id/income_id} not found.")` raises
    were initially skipped on the (false) assumption that
    `pair_selected_as_transfer` is the only UI caller. It is not:
    `ImportService.accept_transfer_pair`
    (`import_service.py`) calls `pair_as_transfer` directly with suggested
    ids and no pre-check, and the import view's `_accept_transfer_pair`
    (`views/import_view/page.py`) toasts any `KaletaError`. A suggested row
    deleted before the click surfaces this toast, so both raises are
    user-facing and are now migrated to `not_found_id` (`{transaction_id}`).
    `set_category_bulk`'s `category_not_found` is likewise migrated (the
    bulk dialog passes a picked id with no pre-check).
- **Format-spec key.** `split_sum_mismatch` keeps the f-string's
  `{remaining:+.2f}` spec in the template; `str.format` (what `t` uses)
  reproduces the exact English fallback, verified in the integration test.
- **Enum-value params.** `category_type_mismatch` / `type_requires_category`
  interpolate the raw enum value (`income` / `Income`), so the Polish
  sentence embeds the English token — the same value the old English message
  showed. Localizing the embedded type word is out of scope for a
  fallback-preserving migration.
- **i18n placement.** `errors.transaction` is a sibling of `errors.payee`,
  added right after it; no `reports`/`common` block touched (avoids textual
  git conflicts with sibling lanes).
- **View changes.** None — `transaction_service` is not a view. The test is
  integration-only and touches no file under `src/kaleta/views/`.
