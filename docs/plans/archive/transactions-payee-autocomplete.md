---
plan_id: transactions-payee-autocomplete
title: Transactions — payee autocomplete and auto-fill on create
area: transactions
effort: medium
roadmap_ref: ../../roadmap.md#transactions
status: archived
archived_at: 2026-09-04
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
  `tests/integration/test_payees.py` (the plan said
  `tests/integration/api/test_payees.py`; no such path has ever existed).

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

### Open questions — all resolved to the plan's defaults

1. **Match by identity?** Deferred, as planned. `match_or_create_by_name`
   matches on `Payee.name` only; it is the single call site to swap when
   `payees-identities-automerge` ships aliases.
2. **Auto-fill scope** — both category and tags.
3. **Toast vs silent** — toast. `transactions.payee_autofilled` names the fields
   it filled and the payee they came from.
4. **Where is `Tag` linked?** `Transaction.tags`, many-to-many via
   `transaction_tags` (`models/tag.py`). Reused as-is; no model change.

### Deviations from the plan, and why

- **The view touchpoint moved.** The plan points at
  `src/kaleta/views/transactions.py` around lines ~394 / ~871; that module has
  since been split into `views/transactions/` (`add_dialog.py`,
  `edit_dialog.py`, `page.py`). Same two dialogs, new files.
- **Service-side auto-fill is tags-only, and the category half lives in the
  dialog.** The plan asks `TransactionService.create` to fill a missing
  category. It cannot: `TransactionCreate.validate_rules` rejects a non-split
  income/expense without a category, and a split parent or a transfer must not
  carry one — so every path that reaches the service either already has a
  category or must not be given one. Writing the branch anyway would have been
  dead code. Tags have no such constraint and are filled in the service, which
  is what makes the API round-trip criterion meaningful. The category is filled
  in the dialog when the payee is picked, which is where the user can see and
  override it — and is what the acceptance criteria describe.
- **The look-up happens *before* the insert, not after.** The plan says "after
  insert". After the insert the new row is itself the payee's most recent
  transaction, so the feature would learn from itself.
- **`payee_name` is on `TransactionUpdate` too.** The plan only lists
  `TransactionCreate`. Without it, a brand-new name typed into the *edit*
  dialog's combobox would be silently dropped. `update` resolves the name the
  same way but never applies learned defaults — the row already holds the
  user's choices.
- **`match_or_create_by_name` is a new method, not a rename of
  `find_or_create`.** They differ where it matters: `find_or_create` matches
  case-*sensitively* because mBank exports arrive ALL-CAPS and each spelling is
  its own payee; the new method folds case in Python (SQLite's `lower()` only
  folds ASCII, so `Żabka`/`żabka` would never match in SQL). The import path
  keeps the old method.
- **The view calls `PayeeService.last_used_for` through `with_session`, not the
  new HTTP endpoint.** Every other view in the repo reaches the service layer
  directly; having a NiceGUI page HTTP-call its own API would be a first. The
  endpoint still ships — it is in the plan's scope, is covered by tests, and is
  what an external client uses. The plan's own wording allows this ("or rebind
  the Python on-change").
- **The payee field is hidden for transfers, in both dialogs.** An internal
  transfer moves money between the user's own accounts and has no counterparty;
  the add dialog builds both legs without one, exactly as the category field is
  hidden there. Review caught that the *edit* dialog had no such rule — it would
  have persisted a payee onto a transfer leg, since `TransactionUpdate` has no
  `validate_rules` to stop it. The field is now hidden there on load and on type
  change, and while hidden the payee is left out of the update entirely rather
  than sent as `None`: clearing it would wipe whatever the CSV import attached
  to the leg. Covered by KAL-TXN-013, which also asserts the stored payee
  survives a save.

### Findings a reviewer should know

- **`deferred_to: q4-2026` was dropped from the frontmatter.** It contradicted
  `status: in-progress` once the plan was picked up; flagged in review as stale
  metadata.

- **`last_used_for` skips rows without a category**, not just transfers. A split
  parent has `category_id = NULL`, so the most recent row could otherwise answer
  "no category" and the feature would look broken. The trade-off: a payee seen
  only on split transactions teaches nothing, including its tags.
- **The seed ships no payees.** The acceptance criteria say *Biedronka* is
  "created by the seed"; `scripts/seed.py` creates no `Payee` rows at all —
  that is `seed-payees-tags-coverage`'s scope (still draft, deferred to
  q4-2026), so seeding them here would poach another plan. The e2e tests seed
  their own payee and category and assert the same behaviour; read the manual
  criteria as "an existing payee" rather than "the seeded one".
- **A payee created from the dialog does not appear in that page's combobox
  until reload.** The options are read once at page load. Retyping the name
  costs nothing — `match_or_create_by_name` folds case and reuses the row, so
  no duplicate can appear. Not worth mutating a live Quasar select's options,
  which keeps a separate deep copy for filtering.
- **One keyboard-only edge case is worth a manual look.** With `add-unique` on
  dict options, if Quasar's *new-value* path ever fires for text that exactly
  matches an existing payee label, NiceGUI keys it by the string, which is not
  among the select's values, and the field clears instead of selecting. In the
  tested flows it does not happen — filtering highlights the match and Enter
  picks it as a normal keyed option — and even if it did, nothing is corrupted:
  `match_or_create_by_name` folds case, so saving still reuses the existing
  payee rather than creating a second one. Listed as a manual check.
- **The options dict is copied per dialog.** `new_value_mode` mutates the dict
  in place; the page hands the same dict to both dialogs, so each select gets
  `dict(payee_options)`.
- **Select indices in `tests/e2e/test_transactions.py` still hold.** The payee
  select is inserted after the account select, and the only positional lookup in
  the suite is `nth(1)` for the account.
- **Making the payee editable made the rule suggester's payee name go stale.**
  `edit_submit` fed `RuleService.suggest_from_corrections` the name captured
  when the row was loaded. That was safe while the payee could not be changed
  here; now a user who corrects both payee and category would have got a rule
  suggested for the *old* payee. It now uses the name as it stands at save time,
  and the `edit_payee_name` holder that only existed for this is gone. Found by
  `i18n-verifier` while auditing the diff.
- **Polish `payee_autofilled` was reworded for case agreement.** `{fields}`
  receives nominative labels (`Kategoria`, `Tagi`), which cannot follow
  "Uzupełniono" — and the labels cannot be inflected, since they are shared with
  every other use of `common.category` / `transactions.tags`. The string now
  uses the colon-list form the repo already uses for the same problem
  (`categories.template_skipped`).
- **The rule suggester falls back to the name the row was loaded with.** The
  edit dialog reads the payee's name from the page-load options; a payee created
  later in the session is not in that dict, so the name would silently be `None`
  and the suggestion would degrade rather than fail. `loaded_payee` keeps the
  name the row opened with as the fallback.
- **The combobox lives in one place.** `views/transactions/payee_field.py`
  holds `build_payee_select()` (both dialogs build the identical widget) and
  `split_payee_value()` (an `int` value means an existing payee, a `str` means
  one the service still has to match or create). Extracted after review flagged
  the two dialogs carrying near-duplicate parsing.
- **Two of the new e2e tests only failed in the full suite.** Both were
  suite-scale fragilities, not feature bugs: a category option virtualised out
  of Quasar's menu once enough categories exist, and a row seeded with an old
  date falling off page 1 of the ledger. The file's scroll-until-found loop is
  now reusable by label (`_select_labeled`), and rows are located through the
  search filter (`_find_row`).

## Implementation

Landed on 2026-09-04 (PR #78).

| SHA | Author | Date | Message |
|---|---|---|---|
| `a8734e3` | Dawid Adamski | 2026-09-04 | Merge pull request #78 from DawidAdamski/plan/transactions-payee-autocomplete |

**Files changed:**
- docs/bdd.md
- docs/plans/transactions-payee-autocomplete.md
- src/kaleta/api/v1/payees.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/schemas/payee.py
- src/kaleta/schemas/transaction.py
- src/kaleta/services/payee_service.py
- src/kaleta/services/transaction_service.py
- src/kaleta/views/transactions/add_dialog.py
- src/kaleta/views/transactions/edit_dialog.py
- src/kaleta/views/transactions/page.py
- src/kaleta/views/transactions/payee_field.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_transactions.py
- tests/integration/test_payees.py
- tests/unit/services/test_payee_service.py
- tests/unit/services/test_transaction_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
