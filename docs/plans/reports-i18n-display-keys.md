---
plan_id: reports-i18n-display-keys
title: Report results carry dimension/metric keys, views resolve them through t()
area: reports
effort: large
status: draft
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
