---
plan_id: import-history-account-coverage
title: Import — per-account import history and coverage view
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
---

# Import — per-account import history and coverage view

## Intent

Dogfooding feedback: *"Ciężko się odnaleźć, które konto już miało
wgrane dane. Łatwo się pogubić, które konto już wczytane miało a które
nie. Dobrze by było mieć listę kont, kiedy ostatnio były w nich dane
wczytywane bądź dodawane i z jaką datą."*

During initial data load (and later, monthly imports) the user juggles
many accounts × many CSV files. Nothing in the app answers: *which
accounts already have data, up to what date, and when did I last touch
them?* The import page shows only the current session's queue; once the
page reloads, that knowledge is gone.

## Current behaviour (code facts)

- There is **no persistent record of imports** — no model, no table
  (`ls src/kaleta/models/ | grep -i import` → nothing). The queue and
  its summary live in page-scope state and vanish on reload.
- `account_service` exposes no "latest transaction date" / "last
  activity" per account; the Accounts view has no such column.

## Scope

- **`ImportRun` model + migration** — one row per completed file
  import: `account_id` (FK), `filename`, `profile`, `imported_count`,
  `skipped_count`, `row_date_min`, `row_date_max`, `created_at`,
  `user_id` (per the user-model groundwork). Written by the import
  service on success — inside the same transaction as the inserts.
- **Account coverage panel on the Import page** — always visible above
  or beside the queue: one row per active account with
  - newest transaction date on the account (computed,
    `max(transactions.date)`),
  - last import (`ImportRun.created_at` + filename), "—" when never
    imported,
  - a subtle "stale" hint when the newest transaction is older than
    N days (default 35; no new setting — constant is fine for v1).
  This directly answers "które konto już wczytane" while building the
  queue.
- **Accounts page column** — "Last activity" (newest transaction date)
  added to the accounts table; sortable, so unloaded accounts cluster.
- **Import history list** — collapsible "Recent imports" section on the
  Import page: last ~20 `ImportRun` rows (date, file, account, imported
  /skipped). No dedicated page; Settings → Data is *not* touched here.
- **Service layer**: `account_service.list_with_activity()` (or extend
  the existing accounts query) returning newest-transaction-date and
  last-import per account in one query — no N+1.
- **BDD**: add `@planned` scenarios `KAL-CSV-008` (after an import, the
  coverage panel shows the account's last import and newest transaction
  date) and `KAL-CSV-009` (Accounts page shows last activity per
  account). Retag when tests land.
- **Backup**: `import_runs` joins backup/restore automatically via
  `Base.metadata.sorted_tables` — verify the round-trip test picks it
  up.

Out of scope: undo/rollback of an import run (future plan; the model's
per-run row is the natural hook), scheduler/reminders ("import overdue"
notifications can ride the wizard-reminders plan later).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_service.py -q`
- `uv run pytest tests/unit/services/test_account_service.py -q`
- `uv run pytest tests/unit/services/test_backup_service.py -q`
- `grep -q "KAL-CSV-008" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Import two files into two accounts, reload the page: the
  coverage panel still shows both imports; a third account with no data
  shows "—" and sorts to the top of "needs attention".

## Touchpoints

- `src/kaleta/models/import_run.py` (new) + `models/__init__.py`
- `alembic/versions/<new>_add_import_runs.py`
- `src/kaleta/services/import_service.py` (write `ImportRun`),
  `src/kaleta/services/account_service.py` (activity query)
- `src/kaleta/views/import_view/` — new `coverage_section.py`,
  `page.py`; `src/kaleta/views/accounts.py` (column)
- `src/kaleta/i18n/locales/en.json` + `pl.json`
- `docs/bdd.md` (KAL-CSV-008…009)
- `tests/unit/services/`, `tests/e2e/test_csv_import.py`

## Open questions

1. Should manual transaction entry also stamp "last activity"? It
   already does implicitly (newest transaction date is computed from
   transactions, whatever their source). Default: **yes, no extra
   work** — document the distinction (last *import* vs last
   *activity*) in the panel labels.

## Implementation notes

_Filled in as work progresses._
