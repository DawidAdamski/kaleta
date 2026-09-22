---
plan_id: reports-trend-columns
title: Reports — trend columns (moving average, change, share, rank)
area: reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md#reports
---

# Reports — trend columns (moving average, change, share, rank)

## Intent

A pivot shows the numbers; it does not say whether they are going
anywhere. "Groceries were 1 840 in August" is a fact, "Groceries are
12 % above their three-month average and climbing for the fourth
month" is the answer. Today that second sentence needs SQL window
functions run outside the app.

Add **derived columns** to the report builder — computed from the
grouped result, switchable per report, saved with it:

| Column | Meaning | Needs |
|---|---|---|
| `share` | value ÷ total of the axis, as % | any report |
| `rank` | position within the axis, largest first | any report |
| `change` | value − previous period, and % | a time axis |
| `moving_avg` | mean of the last N periods (N = 3 default, 3 / 6 / 12) | a time axis |

Every derivation is done in Python over the already-grouped rows
(`ReportResult` or `PivotResult`), never in SQL: the numbers are at
most a few hundred cells, both dialects stay untouched, and the
maths lives in one testable pure function.

## Scope

- **Config**: `ReportConfig.columns: list[Column] = []` where
  `Column = Literal["share", "rank", "change", "moving_avg"]`, and
  `ReportConfig.window: int = 3` for the moving average. `from_dict`
  defaults both, so stored configs stay valid — no migration.
- **Validation**: `change` and `moving_avg` require a time axis
  (`month`, `year`, `weekday` is *not* one — a weekday is a bucket,
  not a sequence). The axis is `dimension` for a single-dimension
  report, `series` for a pivot. When the axis is not a time
  dimension those columns are dropped at execute time and the
  picker greys them out with `reports.column_needs_time_axis`.
- **Computation**: a new pure module
  `src/kaleta/services/report_columns.py` with
  `derive(result, columns, window) -> DerivedResult`. For a
  `ReportResult` the derived values sit beside `values`; for a
  `PivotResult` they are computed **per row along the series
  axis** (so `change` on a *Category by Month* pivot is
  month-over-month for each category, which is the whole point).
  Gaps in a time axis are zero-filled before deriving, so a category
  with no spend in March reads as a 100 % drop, not as a skipped
  month. Percent change from zero is `None` and renders as an
  em dash, not `inf`.
- **Rendering**:
  - `table` → extra columns after the value: `Share`, `#`,
    `Δ` / `Δ %`, `MA(N)`. For a pivot the derived cells appear
    beside each series cell; the picker warns above eight series
    values × two derived columns that the grid gets wide and
    suggests `line`.
  - `bar` → `share` is already what the row bars show (KAL-RPT-002);
    the column is a no-op there. `rank` is the row order. `change`
    and `moving_avg` are not drawn on bars.
  - `line` → `moving_avg` draws as a second, dashed line per series
    in the same hue; `change` is not drawn.
  - The chart title line carries the window when a moving average
    is on: *… over Last 12 Months, 3-month average*.
- **Sentence**: one more optional clause at the end —
  *… top 10, **with share and 3-month average**.* Each column is a
  toggle chip in the picker that opens from that clause.
- **Builder state**: `BUILDER_STATE_DEFAULTS["columns"] = []`,
  `["window"] = 3`; `report_config_from_builder_state` carries both.
- **i18n**: `reports.col_share`, `reports.col_rank`,
  `reports.col_change`, `reports.col_moving_avg`,
  `reports.sentence_with_columns`, `reports.column_needs_time_axis`,
  `reports.window_months` in `en.json` and `pl.json`.
- **BDD**: `KAL-RPT-008` (a moving average on a monthly report adds
  the column and the dashed line), `KAL-RPT-009` (change is per row
  along the series axis on a pivot), `KAL-RPT-010` (columns needing a
  time axis are unavailable on a category report).

Out of scope:
- Year-over-year change (same month last year) as a column — the
  canned `yoy_comparison` covers it; folding it in here is a
  follow-up once the pivot has been lived with.
- Forecast-style projection of the trend — that is the Forecast
  view's job.
- Conditional formatting (red for drops, green for rises) beyond
  the existing signed-amount colouring from
  `transactions-colored-amounts`.
- Export.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_report_columns.py -q`
- `uv run pytest tests/unit/services/test_saved_report_service.py -q`
- `uv run pytest tests/e2e/test_reports_builder.py -q`
- `grep -c "KAL-RPT-0(08|09|10)" -E docs/bdd.md | grep -qE '^[3-9]'`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/kaleta/services/report_columns.py src/kaleta/services/saved_report_service.py src/kaleta/views/reports`
- `uv run ruff check src/kaleta/services/report_columns.py src/kaleta/views/reports`
- `uv run python -c "from kaleta.services.saved_report_service import ReportConfig; c=ReportConfig.from_dict({'dimension':'category'}); assert c.columns == [] and c.window == 3"`
- `[manual]` Dashed moving-average line is distinguishable from the series line in dark mode at the `3e` card size.

## Touchpoints

- `src/kaleta/services/report_columns.py` — new; `derive`, zero-fill of
  time axes, `DerivedResult`.
- `src/kaleta/services/saved_report_service.py` — `ReportConfig.columns`,
  `.window`; `execute` calls `derive` after the query.
- `src/kaleta/views/reports/constants.py` — `COLUMNS` table, state
  defaults.
- `src/kaleta/views/reports/sentence.py` — `columns_label`, trailing
  clause.
- `src/kaleta/views/reports/config_zone.py` — column chips, window
  picker, availability rules.
- `src/kaleta/views/reports/chart_options.py` — dashed MA series.
- `src/kaleta/views/reports/chart_zone.py` — derived columns in the
  table / pivot grid.
- `src/kaleta/i18n/locales/en.json`, `pl.json`.
- `docs/bdd.md` — `KAL-RPT-008`..`010`.
- `tests/unit/services/test_report_columns.py` — new: share sums to
  100, rank ties, change from zero is `None`, zero-fill of a missing
  month, window shorter than history, pivot derivation is per row.
- `tests/e2e/test_reports_builder.py` — the three scenarios.

## Open questions

- Should `moving_avg` include the current period (trailing, N
  periods ending now) or exclude it (baseline to compare against)?
  Trailing is what people expect from "3-month average"; the
  comparison the intent describes ("12 % above its average") wants
  the excluded form. Ship trailing; revisit if the sentence reads
  wrong in dogfooding.
- Does `share` on a pivot mean share of the row total, of the series
  total, or of the grand total? Default: share of the **series**
  total (each month's column adds to 100 %), which matches the
  single-dimension bar view's per-period reading.

## Implementation notes

_Filled in as work progresses._

## Implementation (filled by plan-archiver)
