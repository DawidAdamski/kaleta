---
plan_id: reports-i18n-display-keys
title: Report results carry dimension/metric keys, views resolve them through t()
area: reports
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#reports
---

# Report results carry dimension/metric keys, views resolve them through t()

## Intent
A Polish user reads report headers, labels and pivot columns in English.
`SavedReportService` returns *words*, not keys, so every locale sees the
service's English display strings in the table's column heads, the bar
rows' labels and the pivot's column heads.

## The English strings the service emits
- Column / metric headers built from literals:
  `"Category"`, `"Total Amount"`, `"Count"`, `"Average"`
  (`saved_report_service.py` around `:693–698`, `:744`, `:795`; the
  `TableResult`/`PivotResult` fields `column_header` / `metric_header` /
  `row_header` at `:166`, `:167`, `:184`).
- `_WEEKDAY_NAMES` (`:48`) — English day names, indexed in `_label_of`
  (`:610`) and the bar path (`:623`).
- The `type` dimension's raw enum value (expense / income / transfer).
- The `"Uncategorised"` / `"No Institution"` fallbacks (`:258`, `:260`) and
  `OTHER_ROW_LABEL = "Other"` (`:66`).

The matching keys **already exist** in `en.json`/`pl.json` under `reports.*`
(`dim_category`, `dim_account`, `dim_month`, `dim_year`, `dim_type`,
`dim_institution`, `dim_weekday`, `metric_sum`, `metric_count`,
`metric_avg`, `type_expense`, `type_income`, `type_transfer`; en.json
`:1538–1550`). What is missing is only the plumbing: the results carry the
*key*, and the view calls `t()`.

## Why a plan, not a chore line
This is a **shape change across both result types** (`TableResult` and
`PivotResult`) plus every consumer view
(`src/kaleta/views/reports/{page,chart_zone,config_zone,sentence,…}.py`).
Headers must change from resolved words to dimension/metric keys (and
weekday *ordinals* for the weekday axis), and each render site must resolve
through `t()`. `plan/reports-second-dimension-pivot` already localized the
pivot grid's own row header off the sentence and left the rest alone — this
plan finishes the job.

## Scope
Covers:
- Change the service result fields so they carry **keys/ordinals**, not
  words: `column_header`/`metric_header`/`row_header` become
  dimension/metric keys (e.g. `"dim_category"`, `"metric_sum"`); weekday
  rows carry the ordinal; the `type` dimension carries `type_<enum>`; the
  fallbacks carry stable sentinels the views map to
  `reports.uncategorised` / `reports.no_institution` / `reports.other_row`
  (add these three keys to both locales).
- Resolve every one of those in the report views via `t()` — the layer that
  may touch i18n (rule 10: `t()` lives in views).
- Keep the service free of NiceGUI / `t()` (lint-imports: services must not
  import views/nicegui). The service emits keys; only views translate.
- Update `KAL-RPT-*` scenarios + tests that assert on the English words, and
  add/adjust a scenario asserting Polish rendering.

Does NOT cover:
- Changing which dimensions/metrics exist, or the query logic.
- The `reports_lib` canned-report catalogue wording (separate keys already).
- CSV/export column names (if any read the same headers — called out as an
  Open question).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `uv run pytest tests/unit tests/integration -k "saved_report or report_builder" -n 2 -m "not slow"`
- `grep -q "KAL-RPT" docs/bdd.md`
- `./scripts/verify.sh --e2e` (report views change → rule 8)
- `[manual]` A Polish session reads column heads, bar-row labels and pivot
  column heads in Polish, including weekday names and the
  Uncategorised/No-Institution/Other fallbacks.

## Touchpoints
- `src/kaleta/services/saved_report_service.py` — result dataclasses
  (`TableResult`/`PivotResult`), `_label_of`, `_WEEKDAY_NAMES`, the metric
  and dimension header literals, the fallback labels, `OTHER_ROW_LABEL`.
- `src/kaleta/views/reports/*.py` — resolve keys/ordinals through `t()`.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — add
  `reports.uncategorised`, `reports.no_institution`, `reports.other_row`,
  and weekday-name keys if not already present under a shared namespace.
- `docs/bdd.md`, `tests/` — retag/extend `KAL-RPT-*`.

## Open questions
- Weekday names: is there an existing shared `t()` namespace for day names
  (calendar / planned views) to reuse, or do reports get `reports.weekday_*`?
  Reuse if one exists — do not duplicate day-name strings.
- Do any export/CSV paths read `column_header`/`metric_header` as data? If
  so they must take the English key's *canonical* form, not a localized
  string — resolve before narrowing scope.
- `change` / `share` / `rank` / `moving_avg` derived columns (`Column`
  Literal, `:166`) — do their headers also need keys? Audit during
  implementation.

## Implementation notes
- The invariant to preserve: the **service stays presentation-free**. It
  emits identifiers; the view is the only place `t()` is called. This keeps
  the `views → services` import contract intact (rule 6/10).
- Migrate `TableResult` and `PivotResult` together — they share `_label_of`
  and the weekday path, so a half-migration would leave one rendering words
  and the other keys.

### Decisions taken during implementation

- **Shape of the emitted identifiers.** Headers (`column_header` /
  `row_header` / `series_header` / `metric_header`) carry a bare `reports.*`
  sub-key (`"dim_category"`, `"metric_sum"`); the view calls
  `t(f"reports.{header}")`. Row labels stay `list[str]`, but the
  translatable ones carry a NUL-prefixed **sentinel** so no user-entered
  name (category / account / institution) can collide: `UNCATEGORISED_LABEL`,
  `NO_INSTITUTION_LABEL`, `OTHER_ROW_LABEL`, `WEEKDAY_LABEL_PREFIX+<ordinal>`,
  `TYPE_LABEL_PREFIX+<enum>`. Month/year labels (`2025-01`, `2024`) and real
  names pass through untouched — crucially `report_columns` still parses the
  period strings. A single view helper (`_resolve_label`) maps sentinels →
  `t()`, everything else is returned verbatim; `_localize` applies it to a
  whole result once, so `chart_options` and `build_report_table_data` need no
  change and receive an already-localized result.
- **Where resolution happens.** One place: `chart_zone._localize`, called at
  the top of the refreshable before the result is drawn. `page.py`,
  `config_zone.py` and `sentence.py` render no result header/label text
  (`config_zone` only reads `len(series_labels)`; the sentence is built from
  state, already via `t()`), so they needed no change. The service imports no
  `t()`/nicegui — `lint-imports` stays 4 kept / 0 broken.
- **Weekday namespace (open question).** Reused the existing
  `payment_calendar.wd_full_{mon..sun}` day names rather than duplicating
  Monday…Sunday under `reports.*`. The view maps the Postgres `dow` ordinal
  (0 = Sunday) through `_WEEKDAY_KEYS` to that key. No new day-name strings.
- **Export/CSV audit (open question).** No export path reads
  `SavedReportService`'s headers/labels. The only CSV export in reports is the
  canned-report system (`report_service.py` + `api/v1/reports.py`), which is a
  separate result type and explicitly out of scope. Safe to key-ify.
- **Derived-column headers (open question).** `share` / `rank` / `change` /
  `moving_avg` headers are already localized in `sentence.derived_headers`
  (via `t("reports.col_*")`; `#` and `Δ` are locale-neutral symbols). No
  English leaks there, so they were left as-is.
- **Pivot row header.** `_pivot_grid` now reads the localized `row_header` the
  result carries instead of `dimension_label(state)`, tying the grid's corner
  to the data the last run produced (previously it reached into the sentence
  because the service named columns in English — no longer true).
- **New keys.** Added `reports.uncategorised`, `reports.no_institution`,
  `reports.other_row` to `en.json`/`pl.json` inside the existing `reports`
  object (next to the `type_*` block), to avoid textual conflict with the
  sibling lane adding a top-level `errors` block at end-of-file.
