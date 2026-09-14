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

### The caption says what the file is

Scope asks for `; · UTF-8 · 1 245 rows`, and the step was reusing
`import.mapping_meta` — "Delimiter: ; · 3 columns · showing 10 sample rows".
Two of those three facts describe the *table*, not the file, and the third
was about to be wrong: the table shows four rows while `inspect_csv` samples
ten.

`CsvInspection` gained `total_rows` (counted while sampling, no second pass)
and the caption is a new `import.mapping_sample_caption`. `mapping_meta` is
gone; a leftover key is a key someone re-adds a caption for.

The encoding could not be hard-coded: `auto_decode` tries UTF-8, CP1250 and
ISO-8859-2 in turn, so a file that only decoded as CP1250 must not be
captioned UTF-8. `decode_upload` returns the decoded text *and* the encoding
that worked, `auto_decode` stays as a one-line wrapper for its existing
callers, and the queued file carries the name.

### A cut cell shows the whole value on hover

Open question 2 says "truncated at 32 chars with a tooltip", and the tooltip
needed building: a body slot puts the full value behind a `q-tooltip`, and
only where it differs from the shown one, so a short cell does not grow a
tooltip repeating itself.

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

### A failed file stands on the upload step

The first version sent a failed *generic* file to the mapping step, on the
grounds that its columns were the problem. The page disagrees: it hides the
mapping card for `failed` along with settings and preview, so the line would
have pointed at a step that was not on screen — exactly what
`current_step` exists to prevent. A failed file stands on upload, whatever
read it.

Choosing an account also has to move the line, since that is the whole of
the settings step; `_on_settings_change` refreshes it.

### e2e: the step a fresh upload lands on is not fixed

`test_the_progress_line_says_which_step_i_am_on` asserts that the line
*moves* and that exactly one node is current, rather than naming a step
number. Uploading can fill the settings step in on its own — a target
account is inherited from another queued file or from the last import — so
"three ticked" holds in a clean environment and not in a shared e2e
database. The step numbers themselves are pinned by the unit tests, which
own the state.

### A blocking error is not a footnote

`_render_errors` first put every message in small muted text under the
strip. For a file that needs mapping, those messages are not detail — "Date
column is required" is the thing standing between the user and an import,
and it comes with no row numbers, so no strip appears either. Messages the
strip summarises are muted; messages standing on their own keep the
prominence they had.

### Three scenarios, not two

`KAL-CSV-025` and `KAL-CSV-026` are the plan's. `KAL-CSV-027` is new: the
progress line and the side-by-side layout are the other half of what
artboard 2d changes, and Working Agreement §5 wants user-facing behaviour to
have a scenario.

### The fixture is generic, not mBank

Scope says both new scenarios are automated "on the mBank fixture". The
parse-failure one needs a file whose rows *fail*, and the mBank fixtures are
real, valid exports — breaking one would weaken the tests that depend on it.
`partly-unparseable.csv` is a five-row generic CSV with a bad amount on row
3 and a bad date on row 5, which is what the strip is asserted to name.

### The caption's number is the app's number, and its noun is Polish

Second review round. The caption's row count was formatted in the view with
a hard-coded space for thousands (`f"{n:,}".replace(",", " ")`) whatever the
language, and `pl.json` carried a single "{rows} wierszy" — wrong for every
count ending in 2-4 ("3 wierszy" should be "3 wiersze") and for 1. The count
now uses the same `,` separator as every other figure in the app, and
`row_count_key` picks among `rows_count_one` / `_few` / `_many`, following
the Polish rule (1; 2-4 except 12-14; the rest). The same round removed
`CsvInspection.encoding`, which was added with a `"UTF-8"` default that
`inspect_csv` never filled in and nothing read — `inspect_csv` takes a
decoded `str` and cannot know the encoding, so `QueuedFile.encoding`, set
from `decode_upload` at upload time, is the only source.

### Row numbers are lines, not records

The warning strip presents its numbers as row numbers in the file, but they
came from `enumerate(DictReader, start=2)`, which counts records. A quoted
field containing a newline moves every later line, and the strip would have
sent the reader to the wrong one. `reader.line_num` — the physical line the
record ends on — is what it uses now, with a unit test on a CSV whose second
record spans two lines.

### The parse warning names the mapping, not two columns

`import.parse_warning` ended "check the Date and Amount columns". A file
mapped with separate debit/credit columns fails in `_parse_amount` on those,
with no Amount picker in play at all, so the hint pointed at a field that
was not there. It now says "check the columns you mapped", which is true for
every mapping the step can produce.

### A bank profile's mapping node is done, not skipped

For mbank/pko/wise the mapping card never appears, and `current_step` still
leaves its node behind the user once the file parses. That is deliberate and
documented on `current_step`: the columns *were* mapped, by the profile
rather than by hand, so the step really is behind you — which is all a done
node claims.

### The auto mark follows the importer, not one source of mappings

Third review round. `auto_detected_fields` compared the pickers against
`inspection.detected_mapping` — the header heuristic only. Scope asks for
the mark on fields filled "by profile match or heuristic", so a mapping
applied from a saved import rule got no mark, and one inherited from another
queued file got one wherever it happened to agree with the heuristic. The
file now carries `auto_mapping`: the mapping the importer put there, set at
the three places the machine chooses one — detection on a first parse, a
matched rule, an inherited snapshot — and never on a re-parse that carries
the user's own edits back in. The badge rule itself is unchanged: a field is
auto while the picker still holds what the importer put there.

### A wrapping row does not stack

The two columns carried `flex-wrap md:flex-nowrap`, which never stacked: two
children with `min-w-0` always fit on one flex line, so a narrow screen
squeezed them instead of wrapping. `flex-col md:flex-row` with `w-full` on
each column is what actually stacks. The e2e side-by-side check runs at
desktop width, so nothing catches this but the eye — it belongs to the
`[manual]` pass.

### Blank lines are not rows

`inspect_csv` counts with `csv.reader`, which yields an empty row for a
blank line; `parse_csv` uses `DictReader`, which skips them. A bank export
that ends with a blank line would have been captioned one row larger than it
imports. The count skips them now, and the test asserts the caption's number
against the number of records `parse_csv` finds.

### The plural rule is the app's, not the import view's

`row_count_key` started life in `mapping_section.py`. The rule is language,
not import: it now lives in `kaleta.i18n.plural_key(prefix, count)`, which
any counted caption can use with `<prefix>_one` / `_few` / `_many` keys.

### Not done

The `[manual]` criterion — `test_import.csv` compared to artboard 2d in
light and dark — is the owner's visual pass. Detection logic, bank profiles,
the queue, and the preview and summary steps are untouched, as Scope says.
