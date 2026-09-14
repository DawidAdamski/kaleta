---
plan_id: restyle-import-mapping
title: Restyle — Import progress line and side-by-side mapping with auto badges (artboard 2d)
area: import
effort: medium
status: in-progress
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

### Read this before reviewing the diff

Fifth in a stack — theme-tokens → dashboard → transactions-filter-chips →
budgets-pace-bars → budget-plan-grid → this one. None merged. This plan's
own diff is:

    git diff plan/restyle-budget-plan-grid...HEAD

and its PR is opened with `--base plan/restyle-budget-plan-grid`.

### Open questions — decisions taken

1. **The parse-failure strip reads the whole file, not a sample.** The
   question asked for a sample size, assuming the strip would run its own
   parse. It does not: the file is already parsed by the time the mapping
   step is on screen, and `ParseQueuedFileResult` was carrying the row
   numbers as prose. They are structured now (`error_rows`), so the strip
   costs nothing and covers every row rather than the first 200.
2. **The sample shows raw strings**, mono, cut at 32 characters with the
   whole value on hover — as the default said. Four rows, which is what
   artboard 2d draws and few enough that the picker beside a column stays on
   screen while you read it.

### The auto badge needed no new state

Scope asks for `detected: set[str]` on the mapping state and "a small schema
change". None was needed. `CsvInspection` already carries
`detected_mapping`, and a field is "auto" exactly while the picker still
holds the column detection chose — `auto_detected_fields(detected, current)`
compares the two. A manual change makes them differ, which is the badge
going away, with nothing to keep in sync and nothing to persist.

### The row numbers became numbers

The strip wants "3 rows could not be parsed: 17, 42, 88". The parser knew
those numbers and threw them into a sentence (`f"Row {line_no}: {exc}"`), so
the view's options were scraping its own error strings with a regex or
having the service keep them. `ImportResult.error_rows` and
`ParseQueuedFileResult.error_rows` carry them; the prose messages stay,
below the strip, in muted small text.

### The progress line had to learn where it was

`render_step_indicator()` took no arguments: six numbered pills, every one
identical, telling the reader how many steps exist and nothing about where
they stood. The page never had a "current step" either — it renders every
section and hides the ones that do not apply.

`current_step(active)` in `state.py` is that missing idea, and it reads the
same conditions `_repaint_active` uses to show and hide, so the line cannot
claim a step the page below it is not showing: `needs_mapping` → mapping,
`ready` → settings until an account is chosen and preview after, `done` →
confirm, and a failure lands on mapping for a generic file (its columns are
the problem) or upload for a bank profile (the file is). Eight unit tests.

### e2e: the step a fresh upload lands on is not fixed

`test_the_progress_line_says_which_step_i_am_on` asserts that the line
*moves* and that exactly one node is current, rather than naming a step
number. Uploading can fill the settings step in on its own — a target
account is inherited from another queued file or from the last import — so
"three ticked" holds in a clean environment and not in a shared e2e
database. The step numbers themselves are pinned by the unit tests, which
own the state.

### Three scenarios, not two

`KAL-CSV-025` and `KAL-CSV-026` are the plan's. `KAL-CSV-027` is new: the
progress line and the side-by-side layout are the other half of what
artboard 2d changes, and Working Agreement §5 wants user-facing behaviour to
have a scenario.

### Not done

The `[manual]` criterion — `test_import.csv` compared to artboard 2d in
light and dark — is the owner's visual pass. Detection logic, bank profiles,
the queue, and the preview and summary steps are untouched, as Scope says.
