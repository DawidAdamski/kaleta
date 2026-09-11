---
plan_id: restyle-import-mapping
title: Restyle — Import progress line and side-by-side mapping with auto badges (artboard 2d)
area: import
effort: medium
status: draft
roadmap_ref: ../roadmap.md#import
---

# Restyle — Import progress line and side-by-side mapping

## Intent

`import_view/step_indicator.py` draws six numbered pills; the mapping
step lists field pickers with no view of the data they map. Artboard
`2d` turns the steps into a progress line (done = filled ink circle with
a check, current = filled accent circle with its number, future =
outlined, labels beneath) and makes the mapping step two columns: the
**CSV sample on the left** (delimiter / encoding / row count as a mono
caption, first four rows in a bordered mini-table headed `1: Data`,
`2: Opis`, …) and **field pickers on the right**, so you map a column
while looking at its values. Auto-detected fields get a small `auto`
badge in income colour — the one thing the current screen cannot tell
you. Parse failures surface here as a warning strip naming row numbers
rather than only at Preview.

Depends on `restyle-theme-tokens`.

## Scope

- **Step indicator**: rewrite `render_step_indicator` as a progress line
  (nodes + connecting hairline, labels under nodes, current label in
  ink). Same six steps, same i18n keys.
- **Mapping layout** (`MappingSection`): two columns (stack under `md`).
  Left: caption `; · UTF-8 · 1 245 rows` in `k-mono` from the state's
  detected metadata (`metadata_section.py` already has it), then a
  mini-table of the first 4 rows with `N: <header>` column headers
  (headers from `_col_options`). Right: the existing pickers, one per
  target field, unchanged in behaviour.
- **Auto badge**: pickers whose value came from auto-detection (profile
  match or heuristic in the import service) show an `auto` pill; a
  manual change removes it. Requires the mapping state to carry
  `detected: set[str]` — the import service already knows which fields
  it guessed; expose it on the detection result (small schema change,
  no DB).
- **Parse-failure strip**: when the sample parse reports unparseable rows
  (dates/amounts), render a warning strip (`--k-warning`) above the
  pickers: "3 rows could not be parsed: 17, 42, 88 — check the Date and
  Amount columns". Uses the same parse the Preview step runs, on the
  sample only (first N rows) to stay fast.
- i18n: `import.mapping_sample_caption`, `import.auto_badge`,
  `import.parse_warning`.
- BDD: `KAL-CSV-025` "auto-detected columns are marked" and
  `KAL-CSV-026` "parse failures are listed on the mapping step"
  (@automated via `tests/e2e/test_csv_import.py` on the mBank fixture).

Out of scope: detection logic itself, bank profiles, the queue, preview
and summary steps, per-file mapping memory (all archived plans —
behaviour unchanged).

## Acceptance criteria

- `uv run pytest tests/unit/views/test_import_queue_state.py -q`
- `uv run pytest tests/e2e/test_csv_import.py -q`
- `grep -q "auto_badge" src/kaleta/i18n/locales/pl.json`
- `grep -q "KAL-CSV-025" docs/bdd.md`
- `grep -q "KAL-CSV-026" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Upload `test_import.csv`: progress line shows step 3 in
  accent with 1–2 ticked; sample table on the left with numbered
  headers; `auto` pills on the fields the profile detected; compare to
  artboard `2d` in light and dark.

## Touchpoints

- `src/kaleta/views/import_view/step_indicator.py`,
  `mapping_section.py`, `state.py`, `metadata_section.py`
- `src/kaleta/services/import_service.py` (or the detection module —
  expose detected fields)
- `src/kaleta/schemas/import_*.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `tests/e2e/test_csv_import.py`

## Open questions

1. Sample size for the parse-failure strip? Default: **first 200 rows**
   (matches the preview page size if one exists — confirm).
2. Does the mini-table show raw or already-decoded values? Default:
   **raw strings**, monospace, truncated at 32 chars with a tooltip.

## Implementation notes

_Filled in as work progresses._
