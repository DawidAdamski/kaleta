---
plan_id: import-flow-polish
title: Import — post-import reset, clearer actions, duplicate transparency, dark-mode fix
area: import
effort: small
status: archived
archived_at: 2026-08-11
roadmap_ref: ../roadmap.md#import
---

# Import — flow polish (reset, labels, duplicates, dark mode)

## Intent

Four small dogfooding frictions on the Import page, one PR:

1. *"Jak wczyta się jedno, to F5 nie powinno być krokiem do nowego
   wczytania"* — after a completed import the only way to start a fresh
   one is a full page reload.
2. *"Co ma oznaczać 'Importuj wszystkie'?"* — the button label doesn't
   say what "all" is.
3. *"Na jakiej zasadzie pomija istniejące transakcje (duplikaty)?"* —
   the skip-duplicates checkbox gives no hint what a duplicate is, and
   after import the user only sees a count.
4. *"Wydatki w trybie ciemnym mają niewidoczne tło"* — the
   `📥 Expenses / 📤 Income / 🔄 Transfers` chips above the preview are
   unreadable in dark mode.

## Current behaviour (code facts)

- Queue state lives in page-scope closures
  (`views/import_view/page.py` + `state.py`); there is **no reset
  action** — after `do_import_all()` completes the queue stays in
  "done" state until F5.
- The button is `import.import_btn = "Import all"`
  (`queue_section.py`); it imports every *ready* file in the queue and
  disables itself while running.
- A duplicate is an exact match on **(account, date, amount,
  description)** — `ImportService.find_duplicate()`
  (`services/import_service.py`). This is documented nowhere in the UI;
  the summary shows only `skipped` counts per file.
- The preview chips hard-code Quasar light palette colours:
  `ui.chip(..., color="red-2" / "green-2" / "blue-2")`
  (`preview_section.py`) — light pastel backgrounds that break on the
  dark theme. The mBank metadata banner has the same problem:
  `ui.card().classes("k-info-banner w-full bg-blue-50")`
  (`metadata_section.py`).

## Scope

- **"Start new import" action**: after the queue reaches a terminal
  state (all files done/failed), show a primary button that clears the
  queue, summary, and step indicator back to the Upload step — same
  client, no reload. Also allow "Add more files" while a queue exists
  (upload stays active after import; verify + e2e).
- **Button label**: rename to a count-aware label — "Import N files"
  (i18n plural en+pl, falls back to disabled "Import" with 0); tooltip
  states it imports every file in *Ready* state and skips
  pending/failed ones.
- **Duplicate transparency**:
  - Help icon/tooltip on the skip-duplicates checkbox explaining the
    rule: "a row is skipped when the same account, date, amount and
    description already exist" (i18n en+pl).
  - Per-file expandable "Skipped N duplicates" list in the summary:
    date, amount, description of each skipped row.
    `filter_duplicates()` must return the skipped rows, not just the
    count (service change + unit test).
- **Dark-mode pass on import view**: replace hard-coded `red-2` /
  `green-2` / `blue-2` chip colours and the `bg-blue-50` banner with
  theme-token classes consistent with the app's semantic colours
  (income green, expense red, transfer neutral — cross-cutting
  principle in the roadmap). Verify against both themes; check the
  rest of `import_view/` for other hard-coded light-palette classes
  while in there.
- **BDD**: add `@planned` scenarios `KAL-CSV-010` (user starts a second
  import without reloading), `KAL-CSV-011` (skipped duplicates are
  listed with the matching rule explained), `KAL-CSV-012` (import page
  is readable in dark mode — tag `@manual` if a visual assert is not
  worth an e2e). Retag when tests land.

Out of scope: fuzzy duplicate matching (amount±tolerance, date window —
that heuristic belongs to the transfer/dedupe engines), column mapping
([`import-mapping-wizard`](import-mapping-wizard.md)), import history
([`import-history-account-coverage`](import-history-account-coverage.md)).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_import_service.py -q`
- `grep -q "KAL-CSV-010" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` Import a file, click "Start new import", import another —
  no reload; chips and mBank banner readable in dark **and** light
  mode; skipped-duplicates list matches rows already present in the
  ledger.

## Touchpoints

- `src/kaleta/views/import_view/page.py`, `queue_section.py`,
  `summary_section.py`, `preview_section.py`, `metadata_section.py`,
  `settings_section.py`, `state.py`
- `src/kaleta/services/import_service.py` (`filter_duplicates` return
  type)
- `src/kaleta/views/theme.py` (token classes if a suitable one is
  missing)
- `src/kaleta/i18n/locales/en.json` + `pl.json`
- `docs/bdd.md` (KAL-CSV-010…012)
- `tests/unit/services/test_import_service.py`,
  `tests/e2e/test_csv_import.py`

## Open questions

1. Should "Start new import" keep the last file's account/category
   settings as defaults for the next session (the `queue_inherited`
   mechanism)? Default: **yes** — that is the monthly re-import flow.

## Tests (same PR as the implementation)

Unit (`tests/unit/services/test_import_service.py`):

1. `filter_duplicates` returns skipped `TransactionCreate` rows (not only
   a count) for exact (account, date, amount, description) matches;
   unique rows remain in the first return value.

E2E (`tests/e2e/test_csv_import.py`, docstrings with `Covers: KAL-*`):

2. KAL-CSV-010 — complete an import, click "Start new import", upload
   and import again without reloading.
3. KAL-CSV-011 — seed a matching ledger row, import the CSV with skip
   duplicates on; assert help tooltip text and expandable skipped list
   shows date/amount/description.

KAL-CSV-012 stays `@manual` (visual dark/light assert).

## Implementation notes

- Open Q1: keep last file's account/category settings across "Start new
  import" via `state["last_settings"]` so `inherit_queue_settings` still
  works with an empty queue (monthly re-import flow).
- Dark-mode chips: Quasar `color="red-2"` etc. lose contrast under
  `.body--dark .q-chip` solid override — replaced with `k-stat-chip--*`
  theme tokens. Metadata banner drops `bg-blue-50` in favour of
  light+dark `k-info-banner` styles.
- Button label uses ready-file count only; tooltip clarifies pending/
  failed are skipped.

## Implementation

Landed on 2026-08-11. PR [#47](https://github.com/dadamski/kaleta/pull/47).

| SHA | Author | Date | Message |
|---|---|---|---|
| `5c9d4b9` | Dawid Adamski | 2026-08-11 | feat(import): polish post-import reset, labels, duplicates, dark mode (#47) |

**Files changed:**
- docs/bdd.md
- docs/plans/import-flow-polish.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/import_service.py
- src/kaleta/views/import_view/metadata_section.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/import_view/preview_section.py
- src/kaleta/views/import_view/queue_section.py
- src/kaleta/views/import_view/settings_section.py
- src/kaleta/views/import_view/state.py
- src/kaleta/views/import_view/summary_section.py
- src/kaleta/views/theme.py
- tests/e2e/test_csv_import.py
- tests/e2e/test_rules.py
- tests/e2e/test_transfer_detection.py
- tests/unit/services/test_import_service.py

**Acceptance criteria run** (step 3b):

| Command | Exit |
|---|---|
| `uv run pytest tests/unit/services/test_import_service.py -q` | 0 |
| `grep -q "KAL-CSV-010" docs/bdd.md` | 0 |
| `uv run python scripts/spec_coverage.py` | 0 |
| `bash scripts/verify.sh` | 0 |
