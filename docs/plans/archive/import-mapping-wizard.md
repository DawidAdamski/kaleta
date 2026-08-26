---
plan_id: import-mapping-wizard
title: Import — interactive column-mapping step for generic CSV
area: import
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#import
---

# Import — interactive column-mapping step for generic CSV

## Intent

Dogfooding feedback: *"Brakuje wizarda do wczytywania danych dla CSV. Co
to znaczy 'generyczne'? Trzeba dać możliwość dostosowania."*

Today the "Generic CSV" profile is a black box: the parser guesses
columns via header aliases, and when the guess fails the user gets parse
errors with no way to say "column 3 is the date, column 5 is the
amount". There is no mapping UI at all — the only "customisation" is
choosing between Generic and mBank. The user must be able to *see* what
the parser detected and *correct* it before importing.

## Current behaviour (code facts)

- Profiles: `generic` (header-alias parser) and `mbank` (auto-detected)
  — `services/import_service.py`; registry scaffold from
  [`import-bank-profiles`](import-bank-profiles.md) (in-progress).
- The only hint the user gets is
  `import.upload_hint_generic` — "Supported formats: date, amount,
  description. Negative = expense, positive = income."
- Per-file settings in the queue (`views/import_view/state.py`) hold
  account/categories/skip-flag but **no column mapping**.
- Parse errors land in `QueuedFile.parse_errors` and dead-end the file.

## Scope

- **Mapping step in the wizard** (between Upload and Preview, generic
  profile only; mBank/profile files skip it):
  - Show the first ~10 raw rows of the file with detected delimiter,
    encoding, and header row.
  - One dropdown per target field: date (required), amount (required),
    description (required), payee (optional), counterparty account
    (optional) — pre-selected with the alias-parser's guess when it has
    one.
  - Format controls with sane defaults: date format (auto / common
    presets), decimal separator (`,` / `.`), thousands separator,
    "amounts are negative for expenses" vs separate debit/credit
    columns (two-column amount support may be descoped to an open
    question if effort explodes).
  - Live re-parse on every change: the Preview table and the
    expense/income/transfer chips update from the current mapping, and
    parse errors show inline instead of dead-ending.
- **Explain "Generic"**: replace the profile radio copy with one
  sentence per profile (Generic = "any CSV — you map the columns
  yourself in the next step"); i18n en+pl.
- **Service layer**: extend the generic parser to accept an explicit
  `ColumnMapping` (falling back to today's alias detection when absent)
  — pure function, unit-testable without the UI.
- **Queue integration**: mapping is part of per-file state and is
  inherited by the next queued file the same way account/categories
  already are (`queue_inherited` flow).
- **BDD**: add `@planned` scenarios `KAL-CSV-005` (user maps columns of
  an unrecognised CSV and imports it), `KAL-CSV-006` (mapping step
  pre-fills from alias detection), `KAL-CSV-007` (invalid mapping shows
  inline errors, import stays blocked). Retag when tests land.

Out of scope:
- Persisting mappings between sessions — that is
  [`import-per-file-mapping-memory`](import-per-file-mapping-memory.md),
  which should be implemented **after** this plan and reuse its
  `ColumnMapping` type. This plan supersedes that draft's in-queue
  "column mapping dropdowns" bullet; the memory/rule engine remains
  there.
- New bank profiles ([`import-bank-profiles`](import-bank-profiles.md)).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_service.py -q`
- `grep -q "KAL-CSV-005" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` A CSV with headers the alias parser does not know (e.g.
  Revolut export) imports correctly after manual mapping; the mapping
  step is skipped entirely for an mBank file.

## Touchpoints

- `src/kaleta/services/import_service.py` (`ColumnMapping`, generic
  parser signature, re-parse entry point)
- `src/kaleta/views/import_view/` — new `mapping_section.py`; changes in
  `page.py`, `state.py`, `step_indicator.py`, `profile_section.py`,
  `preview_section.py`
- `src/kaleta/i18n/locales/en.json` + `pl.json` (`import.*` keys)
- `docs/bdd.md` (KAL-CSV-005…007)
- `tests/unit/services/test_import_service.py`, new e2e in
  `tests/e2e/test_csv_import.py`

## Open questions

1. Two-column (debit/credit) amount support in v1? Default: **yes if
   cheap** (one extra dropdown + sign logic), otherwise descope to the
   mapping-memory follow-up.
2. Should the mapping step appear for mBank files whose parse fails?
   Default: **yes** — fall back to generic + mapping instead of a dead
   end.

## Tests (same PR as the implementation)

Unit (`tests/unit/services/test_import_service.py`):

1. Explicit `ColumnMapping` parses a CSV whose headers the alias
   detector does not know (e.g. Revolut-style columns).
2. `detect_column_mapping` / `inspect_csv` pre-fills aliases for known
   headers.
3. Incomplete or invalid mapping returns errors and no ready rows
   (import stays blocked).
4. `inherit_queue_settings` copies `column_mapping` for same-profile
   priors.

E2E (`tests/e2e/test_csv_import.py`, docstrings with `Covers: KAL-*`):

5. KAL-CSV-005 — upload an unrecognised-header CSV, map columns in the
   mapping step, import successfully.
6. KAL-CSV-006 — upload a known-alias CSV; mapping dropdowns are
   pre-filled and preview shows rows without manual remapping.
7. KAL-CSV-007 — leave a required mapping blank (or set an invalid
   combination); inline errors appear and Import stays disabled.

## Implementation notes

- Open Q1: expose debit/credit dropdowns in the mapping UI (parser
  already supports two-column amounts via aliases).
- Open Q2: when mBank parse fails, fall back to generic profile +
  mapping step instead of a dead-end `failed` status.
- New queue status `needs_mapping` — Import button only counts `ready`.
- `ColumnMapping` is a JSON-friendly dataclass (indices + format
  strings) for reuse by `import-per-file-mapping-memory`.
- Mapping-change handlers schedule async re-parse via
  `nicegui.background_tasks` so live preview updates on every dropdown
  change.
- Profile help sentences (`profile_generic_help` / `profile_mbank_help`)
  explain Generic vs mBank under the format buttons.
