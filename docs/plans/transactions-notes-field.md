---
plan_id: transactions-notes-field
title: Transactions — long-form notes alongside description
area: transactions
effort: small
roadmap_ref: ../roadmap.md#transactions
status: draft
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

- Migration applies cleanly on both SQLite (existing dev DBs) and
  PostgreSQL.
- Creating a transaction with `notes="Bought for mum's birthday"`
  persists it; fetching the transaction returns the note.
- Editing a transaction and saving an empty notes field stores
  `NULL` (or empty string — one or the other consistently).
- Transactions list shows a small note icon when `notes` is non-empty;
  clicking the icon opens a tooltip / small drawer with the text.
- The note round-trips via the REST API (`/api/v1/transactions`).
- Existing transactions (`notes=NULL`) render identically to today.

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
_Filled in as work progresses._
