---
plan_id: transactions-payee-autocomplete
title: Transactions — payee autocomplete and auto-fill on create
area: transactions
effort: medium
roadmap_ref: ../roadmap.md#transactions
status: draft
---

# Transactions — payee autocomplete and auto-fill on create

## Intent

The "New transaction" dialog (`src/kaleta/views/transactions.py`)
currently has no payee field. Users have to open the Payees page
separately, create a payee, then come back. Two improvements:

1. **Easy select for existing payees** — replace the missing
   payee field with a NiceGUI combobox that fuzzy-searches the
   existing `Payee` table; picking an entry attaches its
   `payee_id` to the new transaction.
2. **Auto-propagation on create** — when the user picks (or
   types and matches) an existing payee, prefill the
   *category* and any *tags* that were used the last time that
   payee appeared on a transaction. The user can override; the
   prefill is just a learned default.

Together these turn payee management from a chore into a
keyboard-only action: type a few letters, hit Enter, the row is
already 80% filled in.

## Scope

- **Schema** — `TransactionCreate` already has `payee_id`. Add a
  sibling `payee_name: str | None`, used when the user types a
  free-text payee that doesn't match an existing row. The
  service then either matches an existing payee (case-insensitive
  exact name match) or creates one.
- **Service** — extend `TransactionService.create`:
  - If `payee_name` provided and `payee_id` is None, call a new
    `PayeeService.match_or_create_by_name()` and set `payee_id`.
  - After insert, if no category was provided, look up the most
    recent transaction for that payee and copy its `category_id`
    + tags. Only fills missing fields — never overwrites user
    input.
- **Service** — new method `PayeeService.last_used_for(payee_id)`
  returning `(category_id, tag_ids)` from the most recent
  non-transfer transaction.
- **View — New / Edit dialog** in `views/transactions.py`:
  - Add a `ui.input` with `props='clearable'` plus a `ui.menu`
    showing matching payees as the user types. NiceGUI's
    `ui.select(with_input=True, new_value_mode='add')` is the
    idiomatic combobox; use that with options sourced from
    `PayeeService.list()` cached at dialog-open time.
  - Position the field directly above the category field so
    Tab order matches mental flow: amount → payee → category.
  - When a payee is picked, fire a small JS-side handler (or
    rebind the Python on-change) that:
    - looks up `last_used_for(payee_id)` via a new tiny API
      endpoint (`GET /api/v1/payees/{id}/last-used`);
    - if the category select is empty, sets it;
    - if the tags multi-select is empty, sets it.
- **API** — `GET /api/v1/payees/{id}/last-used` returns
  `{category_id, tag_ids: [...]}` or 404 if the payee has no
  prior transactions.
- **Edit dialog** — same combobox, but no auto-fill (user is
  editing an existing row; we do not overwrite).
- **i18n** — `transactions.payee_field`, `transactions.payee_hint`,
  `transactions.payee_autofilled` (toast when auto-fill happened
  so the user knows what changed).
- **Tests** —
  - Unit: `PayeeService.match_or_create_by_name` exact / new.
  - Unit: `PayeeService.last_used_for` returns the category +
    tags of the most recent transaction (skipping transfers).
  - Unit: `TransactionService.create` auto-fills only when fields
    are empty; user-supplied values win.
  - API: `GET /api/v1/payees/{id}/last-used` happy-path + 404.

Out of scope:
- Fuzzy matching at the model level (already handled by
  `payees-identities-automerge` plan).
- Auto-fill from CSV import — that flow already has its own
  payee-mapping step.
- Suggesting tags by description text (out of scope; payee-driven
  only).

## Acceptance criteria

- Opening "New transaction", typing "biedr" and pressing Enter
  selects the existing *Biedronka* payee (created by the seed).
- The category select is populated with *Żywność* (the most
  recent category seen for that payee).
- Editing a transaction shows the same combobox but does not
  auto-fill anything.
- Typing a brand-new payee name and confirming creates the
  payee row and links it.
- A toast `transactions.payee_autofilled` shows once when the
  auto-fill happens, with the names of the filled fields, so
  the user can revert if undesired.
- Round-trip via the REST API works.

## Touchpoints

- `src/kaleta/schemas/transaction.py` — add `payee_name`.
- `src/kaleta/services/transaction_service.py` — extend `create`.
- `src/kaleta/services/payee_service.py` — add
  `match_or_create_by_name`, `last_used_for`.
- `src/kaleta/api/v1/payees.py` — new `last-used` endpoint.
- `src/kaleta/views/transactions.py` — new combobox in `ui.dialog`
  around line ~394 and ~871 (add + edit).
- `src/kaleta/i18n/locales/{en,pl}.json` — 3 keys.
- `tests/unit/services/test_transaction_service.py`,
  `tests/unit/services/test_payee_service.py`,
  `tests/integration/api/test_payees.py`.

## Open questions

1. **Match by identity?** The `payees-identities-automerge`
   plan introduces aliases. Default: **defer** — match on
   `Payee.name` only in this plan; once identities ship, this
   plan's `match_or_create_by_name` swaps over.
2. **Auto-fill scope** — category only, or also tags? Default:
   **both**. Tags are cheap to override.
3. **Toast vs silent** — silent risks confusion when category
   "magically" appears. Default: **toast** with explicit
   "auto-filled from previous *Biedronka* transaction".
4. **Where is `Tag` linked on transactions?** Verify
   `Transaction.tags` relationship name and reuse — model has
   it; tests already exist.

## Implementation notes
_Filled in as work progresses._
