---
plan_id: transactions-notes-field
title: Transactions — long-form notes alongside description
area: transactions
effort: small
roadmap_ref: ../roadmap.md#transactions
status: in-progress
deferred_to: q4-2026
---

# Transactions — long-form notes alongside description

## Intent

`Transaction.description` is the short, bank-imported line. Users
frequently want to keep a second, longer note — context, reason,
receipt reference, person's name, follow-up reminder — without
corrupting the description (which should stay close to what the
bank sent). Add a dedicated `notes` field to `Transaction` and
expose it as an optional textarea wherever the user adds or edits
a transaction.

## Scope

- **Model** — add `notes: Mapped[str | None]` (nullable, no length
  cap beyond the DB default `TEXT`) to `src/kaleta/models/transaction.py`.
- **Schema** — add `notes: str | None = None` to
  `TransactionCreate`, `TransactionUpdate`, `TransactionResponse` in
  `src/kaleta/schemas/transaction.py`.
- **Migration** — new Alembic file adding a nullable `notes` TEXT
  column. Compatible with SQLite + PostgreSQL.
- **Service** — `TransactionService.create / update` pass-through;
  no derived logic.
- **Import CSV** — leave `notes` NULL by default; CSV column mapping
  can optionally point a column at `notes`.
- **View: Transactions list** — a small icon in the row when a
  transaction has notes; tooltip or drawer shows the note content.
- **View: New/Edit transaction dialog** — add an optional textarea
  below the description field, labelled "Notes (optional)". Keyboard
  shortcut: `Ctrl+Shift+N` to focus the notes field (non-collision
  with existing shortcuts — verify).
- **i18n** — `transactions.notes`, `transactions.notes_hint`,
  `transactions.has_notes_tooltip`.
- **Tests** — new unit tests:
  - `TransactionService.create` accepts notes and round-trips them.
  - `TransactionUpdate` can clear notes with `notes=None`.
  - Schema validation on over-length notes (if we add a length cap).

Out of scope:
- Rich text / markdown rendering — plain text only.
- Notes on planned transactions (future plan if useful).
- Full-text search over notes — notes are shown on demand, not
  filtered.
- Notes on splits — one note per transaction, not per split.

## Acceptance criteria

Executable (the DoD gate and `plan-archiver` run these):

- `ls alembic/versions | grep -q notes`
- `grep -q "notes" src/kaleta/models/transaction.py`
- `grep -q "notes" src/kaleta/schemas/transaction.py`
- `uv run pytest tests/unit/services/test_transaction_service.py -q -k notes`
- `uv run pytest tests/integration/test_transactions.py -q -k notes`
- `grep -q '"has_notes_tooltip"' src/kaleta/i18n/locales/en.json`
- `grep -q '"has_notes_tooltip"' src/kaleta/i18n/locales/pl.json`
- `grep -qE "KAL-TXN-007 @(automated|manual)" docs/bdd.md`
- `grep -qE "KAL-TXN-008 @(automated|manual)" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

Behaviour the tests above must pin down:

- Creating a transaction with `notes="Bought for mum's birthday"`
  persists it; fetching returns the note (service unit test, `-k notes`).
- Updating with `notes=None` clears the note; empty string is normalised
  to `NULL` (one representation only — assert it).
- The note round-trips via `POST`/`GET /api/v1/transactions`
  (integration test, `-k notes`).
- Existing rows (`notes=NULL`) keep rendering identically — covered by
  the existing e2e suite staying green.

Manual (owner, before archiving):

- `[manual]` Migration applies cleanly on an existing SQLite dev DB and
  on PostgreSQL (CI postgres job green).
- `[manual]` Transactions list shows the note icon only when `notes` is
  non-empty; clicking/hovering shows the text (KAL-TXN-007).
- `[manual]` `Ctrl+Shift+N` focuses the notes field in the dialog and
  does not collide with existing shortcuts.

## Touchpoints

- `src/kaleta/models/transaction.py` — add column.
- `src/kaleta/schemas/transaction.py` — add field to 3 schemas.
- `alembic/versions/NNN_add_transaction_notes.py` — new migration.
- `src/kaleta/services/transaction_service.py` — no change expected
  beyond schema pass-through.
- `src/kaleta/api/v1/transactions.py` — double-check the endpoint
  serialises notes; should be automatic via the Pydantic schema.
- `src/kaleta/views/transactions.py` — add textarea in the edit
  dialog, add icon in the row, optional keyboard shortcut.
- `src/kaleta/i18n/locales/{en,pl}.json` — 3 keys each.
- `tests/unit/services/test_transaction_service.py` — round-trip
  tests.

## Open questions

1. **Length cap?** None vs. e.g. 4 000 chars. Default: **none** —
   DB `TEXT` handles long content; users rarely hit limits.
2. **Note indicator in the row** — icon only, or truncated preview
   in a muted row below the description? Default: **icon only** to
   keep the table compact.
3. **Notes field in CSV import** — add a dropdown item in the
   column mapper? Default: **yes**, harmless and lets power users
   import bank memos.

## Implementation notes

### Open questions — resolved

1. **Length cap?** Default taken: **none**. The column is `sa.Text()`, the
   Pydantic field carries no `max_length`, and
   `test_create_keeps_long_notes_uncapped` pins a 10 000-character note
   round-tripping intact.
2. **Note indicator in the row** — default taken: **icon only**. A
   `sticky_note_2` `q-icon` (class `notes-row-icon`) sits left of the
   description cell, mirroring how the split indicator sits in the category
   cell. Its `q-tooltip` carries the note text; the icon's `aria-label` is
   `transactions.has_notes_tooltip` ("Has notes"), which is what the e2e test
   and screen readers key off. No truncated preview row — the table stays
   compact.
3. **Notes field in CSV import** — default taken: **yes**. `ColumnMapping`
   gained a `notes` index (persisted through `to_dict`/`from_dict`), the
   generic parser fills `ParsedRow.notes`, `to_transaction_creates` passes it
   through, and the mapping step shows a "Notes" dropdown. Deliberately
   **not** added to `_DESC_ALIASES`-style auto-detection: the plan says
   imports leave `notes` NULL by default, so a column only lands in `notes`
   when the user picks it.

### Decisions a reviewer should know

- **One empty representation.** Normalisation lives in the schema, not the
  service: `Notes = Annotated[str | None, AfterValidator(_normalise_notes)]`
  strips the value and maps `""` / whitespace-only to `None`. It is applied to
  both `TransactionBase` (so `TransactionCreate` and `TransactionResponse`
  inherit it) and `TransactionUpdate`, which is what makes "clear the textarea
  and save" (KAL-TXN-008) clear the column — the dialog sends `""`, the schema
  turns it into `NULL`. `TransactionUpdate` still uses `exclude_unset`, so an
  update that does not mention `notes` leaves an existing note alone
  (`test_update_without_notes_keeps_existing_notes`).
- **No service change.** `create` / `update` already pass whole schema dumps
  to the model, so `notes` flows through without touching
  `TransactionService`. The only service edit is `build_table_row`, which now
  emits `notes` and `has_notes` for the row indicator.
- **Keyboard shortcut.** The plan asked for `Ctrl+Shift+N` and told me to
  verify non-collision. It *does* collide, but not with anything in Kaleta —
  Chrome and Edge claim `Ctrl+Shift+N` for a new incognito/InPrivate window
  and never deliver the keydown to the page, and Firefox uses it for "restore
  closed window". So both dialogs bind `Ctrl+Shift+N` **and** `Alt+Shift+N`
  (`ui.keyboard(..., ignore=[])`, guarded on the dialog being open).
  `Alt+Shift+N` is the one that reliably reaches the page in a browser and is
  what the e2e test asserts; `Ctrl+Shift+N` still works in `KALETA_MODE=app`
  and in browsers that do not reserve it. No collision with the page's
  existing `Alt+N` (new transaction) or `PageUp`/`PageDown` paging.
- **Transfers carry the note on both legs**, the same rule `description`
  already follows, so the note is visible from either account.
- **The add dialog clears the notes textarea on hide.** `description` is not
  reset today, but a long-form note silently carried into the next entry is a
  worse failure than a stale one-line description — an autogrow textarea below
  the fold is easy to miss. Left the existing description behaviour alone
  (out of scope).
- **BDD housekeeping.** KAL-TXN-007 / KAL-TXN-008 were sitting *outside* the
  Gherkin code fence in `docs/bdd.md` (the fence closed after KAL-TXN-006).
  Moved them inside and retagged `@planned` → `@automated`; both are covered
  by `tests/e2e/test_transactions.py::test_add_note_then_clear_it`. KAL-TXN-007's
  last step now reads "hovering the icon" rather than "opening the icon",
  matching the tooltip that was built.
- **Migration** `j4k5l6m7n8o9_add_transaction_notes` adds one nullable
  `sa.Text()` column — no server default, no backfill, so existing rows stay
  `NULL` and render exactly as before. Verified `upgrade head` then
  `downgrade -1` on a fresh SQLite file.
