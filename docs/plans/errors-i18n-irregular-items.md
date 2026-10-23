---
plan_id: errors-i18n-irregular-items
title: Localize irregular_item_service error toasts
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Localize irregular_item_service error toasts

## Intent
A follow-up slice of [`errors-i18n-message-keys`](archive/errors-i18n-message-keys.md),
which shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort
(payee identity / merge-undo). The next slice migrated `transaction_service`
([`errors-i18n-transactions`](errors-i18n-transactions.md)). This slice
migrates **only** `src/kaleta/services/irregular_item_service.py`: its
user-facing `KaletaError` raises now carry an `errors.irregular_item.*` key
so a Polish session reads the toast in Polish, while logs, event capture and
the API keep reading the English `exc.message`.

## Scope
Covers:
- `irregular_item_service.py`: add `message_key="errors.irregular_item.<slug>"`
  (+ `params` where the message interpolates) to each user-facing raise,
  keeping the existing English string as the positional `message` fallback.
- The `errors.irregular_item` block in `en.json` and `pl.json` (14 keys).
- `docs/bdd.md`: `KAL-ERR-003` + a covering integration test.

Does NOT cover:
- Any other service (each gets its own follow-up slice — the `chores.md`
  line stays open until all services are done).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still emits the English `message`).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-003" docs/bdd.md`
- `uv run pytest tests/integration -k "error_i18n" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/irregular_item_service.py` — migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.irregular_item.*`.
- `docs/bdd.md` — `KAL-ERR-003`;
  `tests/integration/test_error_i18n_irregular_items.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes
- **Slice boundary.** This covers `irregular_item_service` only; the parent
  plan's "remaining services get their own follow-up slices" is honoured.
  `chores.md` follow-up line stays unticked.
- **Caller map (how each raise reaches a toast).** `IrregularItemService`
  has exactly two call sites outside the service, both user-driven:
  - `views/irregular_fund.py` — the fund page. Calls `plan`, `create`,
    `delete`, `record_payment`, `link_payment`, `create_funding_plan`,
    `history`, `items`. Every `KaletaError` out of these toasts via the
    view's error handling.
  - `services/annual_review_service.py` — `commitments()`/`adjust()`/`drop()`
    call `items`, `update`, `delete`, which reach `_fund`/`_item`. That
    service's sole caller is `views/annual_review.py` (also a toast path).
  - No API route references the service (`grep` over `src/kaleta/api`
    returns nothing), so the API-contract concern does not apply here.
- **Migrated raises (14 keys over 14 raise statements — all of them):**
  - `_fund` — `fund_not_found` (`{fund_id}`), `not_irregular_fund`. Reached
    from both callers with a page/URL-supplied `fund_id` (a deleted or
    non-irregular fund surfaces these).
  - `_item` — `item_not_found` (`{item_id}`). Reached via `update`/`delete`
    (view + annual review) with a row that may have been deleted concurrently.
  - `create_funding_plan` — `fund_needs_account`, `add_item_before_planning`,
    `source_must_differ`, `account_not_found`, `transfer_already_planned`,
    `planned_transfer_not_found`. All from the funding-plan dialog.
  - `_fund_account` — `fund_no_account` (via `record_payment`/`link_payment`/
    `history`).
  - `_fund_item` — `item_other_fund` (via `record_payment`/`link_payment`).
  - `record_payment` — `payment_needs_category`.
  - `link_payment` — `transaction_not_found` (`{transaction_id}`),
    `only_expense_is_payment`.
- **No skipped raises.** Unlike the transaction slice (which kept three
  post-commit `KaletaError` invariants English), this service has no
  post-commit/developer-only raise: every `raise` sits on a validation or
  lookup path that a user action can hit, so all 14 were migrated. In
  particular `planned_transfer_not_found` is *not* a post-commit invariant —
  it is a genuine (if rare) race between `planned.list()` and
  `planned.update()` (a concurrent delete of the existing transfer), so it
  gets a key rather than being treated as unreachable. Following the
  parent-plan rule "when unsure, migrate it", borderline raises
  (`not_irregular_fund`, reachable only by URL manipulation) are migrated
  too — the English fallback is unchanged and a key never hurts.
- **Behaviour-neutral.** No `code` value, control-flow or message string
  changed. Each English fallback is byte-identical to the pre-migration
  literal; the integration test asserts `t(exc.message_key, **exc.params)
  == exc.message` in English for driven raises, so a raise-site key/param
  typo fails the suite.
- **i18n placement.** `errors.irregular_item` is a sibling of
  `errors.transaction`, added right after it inside the `errors` block; no
  `reports`/`common`/`dashboard` block touched (avoids textual git conflicts
  with sibling lanes).
- **View changes.** None — `irregular_item_service` is not a view. The test
  is integration-only and touches no file under `src/kaleta/views/`.
</content>
</invoke>
