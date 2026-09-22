---
plan_id: reports-second-dimension-pivot
title: Reports — second dimension and pivot table
area: reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md#reports
---

# Reports — second dimension and pivot table

## Intent

The report builder answers one question shape: *one dimension × one
metric*. "Spending by category this year" is one click; "spending by
category **per month** this year" is not a report at all — it is
twelve reports run by hand, or a `sqlite3` session next to the app.
The question people actually bring to a finance app is almost always
two-dimensional: how does each category move month to month, which
account carries which category, how does weekday spend split by type.

Add an optional **second dimension** (`series`) to `ReportConfig`. With
it set, the result is a matrix — rows from `dimension`, columns from
`series` — rendered as a pivot table, a stacked bar or a multi-line
chart. The sentence gains one more underlined word: *Show Total Amount
grouped by Category **by Month** for Expense over This Year.*

Without `series` nothing changes: existing saved reports load, run and
render exactly as today.

## Scope

- **Config**: `ReportConfig.series: Dimension | None = None`
  (`saved_report_service.py`). `to_dict` / `from_dict` round-trip it;
  `from_dict` defaults to `None` so every stored `saved_reports.config`
  JSON stays valid — no migration.
- **Validation**: `series` must differ from `dimension`. `top_n`
  applies to the row axis only (the top-N rows by their row total);
  the series axis is never truncated. Time dimensions (`month`,
  `year`, `weekday`) are ordered chronologically on either axis;
  everything else by row total, largest first, as today.
- **Service**: `SavedReportService.execute` grows a second path.
  `_execute_on_transactions` / `_execute_on_flows` select
  `(row_label, series_label, metric)` grouped by both expressions,
  reusing `_dimension` / `_flow_dimension` for each axis (the two
  join lists are merged, deduplicated by table). The result type
  gains a matrix form:

  ```python
  @dataclass(frozen=True)
  class PivotResult:
      row_header: str            # "Category"
      series_header: str         # "Month"
      row_labels: list[str]
      series_labels: list[str]
      cells: list[list[float]]   # [row][series], missing pairs are 0.0
      metric_header: str
      row_totals: list[float]
      series_totals: list[float]
  ```

  `execute` returns `ReportResult | PivotResult`; callers branch on
  the type. Row/series ordering and top-N cut happen in Python after
  the grouped query — the SQL stays one `GROUP BY a, b` on both
  dialects, and `sql_compat` gains nothing.
- **Charts** (`views/reports/chart_options.py`, `chart_zone.py`):
  - `table` → pivot grid: first column row labels, one column per
    series value, a trailing **Total** column and a **Total** footer
    row. Amounts through `spaced_thousands`.
  - `bar` → stacked bars: one bar per row, one segment per series
    (ECharts `stack`). Legend lists the series.
  - `line` → one line per row label over the series axis. Only
    offered when `series` is a time dimension; otherwise the chart
    type picker disables `line` with a tooltip.
  - `pie` / `donut` → not available with a series set; the picker
    disables them the same way. Selecting a series while `pie` /
    `donut` is active switches the chart type to `bar`.
  - Palette: series colours from `views/reports/palette.py`, one hue
    per series value, stable across runs of the same report.
- **Sentence** (`views/reports/sentence.py`, `config_zone.py`): a
  new optional word after the grouping — *by Month* — that is a
  drop target and a picker like the grouping word. When unset it
  reads as a faint *+ by …* affordance, not as a blank.
- **Builder state**: `BUILDER_STATE_DEFAULTS["series"] = None`;
  `report_config_from_builder_state` carries it over.
- **i18n**: `reports.series_by`, `reports.series_none`,
  `reports.pivot_total`, `reports.chart_needs_time_series`,
  `reports.chart_unavailable_with_series` in `en.json` and `pl.json`.
- **Seed**: no change — the demo ledger already spans six years
  and enough categories to make the pivot read.
- **BDD**: `KAL-RPT-005` (a series turns the table into a pivot with
  totals), `KAL-RPT-006` (stacked bar carries a legend of series
  values), `KAL-RPT-007` (a saved report without `series` loads
  unchanged) added to `docs/bdd.md` and covered by
  `tests/e2e/test_reports_builder.py`.

Out of scope:
- Derived columns (moving average, month-over-month change, share,
  rank) — [reports-trend-columns](reports-trend-columns.md).
- A third dimension, nested groupings, or sub-totals per group.
- CSV / XLSX export of the pivot — the builder has no export today;
  adding one is its own plan.
- Any change to `ReportService` and the canned reports it feeds
  (dashboard, YTD, YoY). `yoy_comparison` is the one canned report
  that is already a two-dimensional matrix; it stays as is.
- Categorised-flows semantics: with `series` set, category splits
  are attributed exactly as the single-dimension flows path does
  today, no new rules.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_saved_report_service.py -q`
- `uv run pytest tests/e2e/test_reports_builder.py -q`
- `grep -c "KAL-RPT-00[567]" docs/bdd.md | grep -qE '^[3-9]'`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/kaleta/services/saved_report_service.py src/kaleta/views/reports`
- `uv run ruff check src/kaleta/services/saved_report_service.py src/kaleta/views/reports`
- `uv run python -c "from kaleta.services.saved_report_service import ReportConfig; assert ReportConfig.from_dict({'dimension':'category'}).series is None"`
- `[manual]` Pivot table on artboard `3e` layout: row labels left-aligned, amounts right-aligned, Total column and footer visually distinct from data cells, in both themes.
- `[manual]` Stacked bar with 12 months × 8 categories stays legible at the `3e` card width; legend wraps rather than clips.

## Touchpoints

- `src/kaleta/services/saved_report_service.py` — `ReportConfig.series`,
  `PivotResult`, second execute path, ordering + top-N in Python.
- `src/kaleta/views/reports/constants.py` — `BUILDER_STATE_DEFAULTS["series"]`.
- `src/kaleta/views/reports/sentence.py` — `series_label`, sentence word.
- `src/kaleta/views/reports/config_zone.py` — series picker / drop target,
  chart-type availability rules.
- `src/kaleta/views/reports/chart_options.py` — stacked bar, multi-line.
- `src/kaleta/views/reports/chart_zone.py` — pivot grid rendering.
- `src/kaleta/views/reports/palette.py` — per-series colours.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — keys listed above.
- `docs/bdd.md` — `KAL-RPT-005`..`007`.
- `tests/unit/services/test_saved_report_service.py` — matrix shape,
  zero-fill of missing pairs, chronological ordering of time axes,
  top-N on rows only, `from_dict` backward compatibility, flows path
  with splits.
- `tests/e2e/test_reports_builder.py` — the three scenarios.
- No migration: `saved_reports.config` is free-form JSON.

## Open questions

- Should `top_n` on the row axis fold the cut-off rows into an
  **Other** row so the series totals still add up to the ledger?
  Leaning yes: a pivot whose column totals do not match the
  single-dimension report of the same query would read as a bug.
- Does the dashboard's report widget (if any saved report can be
  pinned there) need to render `PivotResult`, or should pinning be
  limited to single-dimension reports for now? Check
  `views/dashboard` before starting; default to the limitation.
- Month labels on the series axis: `date_year_month` returns
  `YYYY-MM`; the pivot header would read better as `Jan 26`. Decide
  with the sentence's existing period formatting so both agree.

## Implementation notes

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
