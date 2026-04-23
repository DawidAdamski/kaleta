---
plan_id: import-per-file-mapping-memory
title: Import — per-file mapping with filename-based memory
area: import
effort: medium
roadmap_ref: ../roadmap.md#import
status: draft
---

# Import — per-file mapping with filename-based memory

## Intent

The multi-file import queue (shipped earlier) accepts several CSV
files in one go, but two gaps remain:

1. **No per-file mapping** — when the user uploads
   `mbank-2025-10.csv` alongside `pko-2025-10.csv`, the wizard
   can't tell them the account / column mapping for each file, so
   both must share the same settings or be imported one at a time.
2. **No memory** — next month the user uploads the same-shape files
   again; they have to re-configure mappings every single import.
   Banks' CSVs don't change shape, so re-teaching is pure friction.

Add per-file mapping in the queue UI, plus a rule engine that
remembers mappings based on filename patterns and auto-applies them
on subsequent imports.

## Scope

- **Per-file row in the queue** — for each uploaded file in the
  current session, the queue displays:
  - Filename, size, detected format/encoding.
  - Account dropdown (which Kaleta account receives the
    transactions).
  - Column mapping dropdowns (date, amount, description, payee,
    …) — pre-populated from any matching saved rule, editable.
  - Status (pending / applied / error).
- **Bulk defaults row** at the top — optional; lets the user set
  a default account and mapping for *all* files in this session
  that don't already have one inferred from a saved rule. A row's
  individual settings always override the bulk default.
- **Save mapping rule** — on import completion, a checkbox
  "Remember this mapping" (default: checked) creates / updates a
  `ImportRule` row with:
  - `filename_pattern`: `str` — fnmatch-style pattern derived from
    the filename (e.g. `mbank-*.csv`). The user can edit the
    suggested pattern inline before saving.
  - `account_id`
  - `column_mapping: dict[str, int]`
  - `encoding`, `delimiter` if non-default
  - `last_used_at`, `created_at`
- **Rule matching** — on upload, each file runs through the saved
  rules:
  - First match (by most-specific pattern; ties broken by
    `last_used_at` desc) wins.
  - The matched rule's fields populate the queue row; the user
    can still edit before applying.
- **Rule management UI** — Settings → Import tab gains a new
  section "Saved import rules" with:
  - List of rules (pattern, account, column summary,
    last-used date).
  - Delete / edit actions.
  - Toggle to enable/disable a rule without deleting.
- **Model**: new `ImportRule` table — `id`, `filename_pattern`,
  `account_id FK`, `column_mapping JSONB`, `encoding`,
  `delimiter`, `is_active BOOL`, `last_used_at`, `created_at`.
  SQLite-compatible (`JSONB` falls back to `JSON`).
- **Alembic migration**.
- **Service**: `ImportRuleService` with CRUD + a
  `match(filename)` method.
- **Schemas**: `ImportRuleCreate / Update / Response`.
- **API**: `/api/v1/import-rules` CRUD.
- **i18n** — all new strings.
- **Tests** — unit tests for `match()` (most-specific wins,
  case-insensitive, disabled rules skipped).

Out of scope:
- Regex-based patterns — fnmatch is enough for filenames.
- Mapping by file *content* (first-line signature) — filename is
  sufficient for Polish banks' static export naming.
- Auto-categorisation rules — handled separately in Transactions.
- Transfers detection across imported files.
- Multi-account detection inside a single file.

## Acceptance criteria

- Uploading `mbank-2025-10.csv` + `pko-2025-10.csv` in one session
  displays two queue rows; each has its own account + column
  mapping UI.
- Filling in a mapping and saving creates an `ImportRule` with a
  filename pattern suggested as `mbank-*.csv` (the user can edit
  before confirming).
- Next month, uploading `mbank-2025-11.csv` auto-populates the
  queue row from the saved rule; the user can still override.
- Two matching rules: the one with the more specific pattern
  (longer common prefix) wins; ties broken by `last_used_at`.
- Disabling a rule in Settings stops it from matching but keeps
  it in the list.
- Deleting a rule removes it permanently.
- Bulk defaults row: setting `Account = X` and uploading three
  files with no matching rules applies `X` to all three; a fourth
  file that matches a saved rule keeps the rule's account
  instead.

## Touchpoints

- `src/kaleta/models/import_rule.py` — new model.
- `src/kaleta/schemas/import_rule.py` — new schemas.
- `src/kaleta/services/import_rule_service.py` — new service.
- `src/kaleta/services/import_service.py` — existing import
  service consults `ImportRuleService.match(filename)` when a
  file enters the queue.
- `alembic/versions/NNN_add_import_rules.py`.
- `src/kaleta/views/import_view.py` — queue row UI, per-file
  editors, "Remember" checkbox.
- `src/kaleta/views/settings.py` — new "Saved import rules"
  section under the Import tab.
- `src/kaleta/api/v1/__init__.py` — register new router.
- `src/kaleta/api/v1/import_rules.py` — new router.
- `src/kaleta/i18n/locales/{en,pl}.json` — ~20 new keys.

## Open questions

1. **Pattern specificity metric** — longest common prefix,
   prefix-length, or fnmatch-wildcard count? Default: **longer
   non-wildcard prefix wins**; ties by `last_used_at` desc.
2. **Pattern case sensitivity** — treat `MBANK-*.CSV` and
   `mbank-*.csv` as the same? Default: **case-insensitive** for
   pattern and filename.
3. **Suggested pattern algorithm** — take everything up to the
   first digit block, replace with `*`? Default: **yes** —
   `mbank-2025-10.csv` → `mbank-*.csv`. The user can edit.
4. **Apply rule silently, or show a "Applied rule X" banner?**
   Default: **subtle chip on the row** ("Rule: mbank-*.csv").
5. **Mapping storage format** — keyed by target field (`{"date": 0,
   "amount": 2, ...}`) or list positional? Default: **keyed
   dict** for clarity.

## Implementation notes
_Filled in as work progresses._
