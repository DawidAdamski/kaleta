---
plan_id: reports-topn-label-with-trend
title: Report builder — the top-N clause tells the truth on a trend report
area: reports
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#reports
---

# Report builder — the top-N clause tells the truth on a trend report

## Intent
On a one-dimensional month/year report with a change or moving-average column
on, the engine ignores `top_n` — a sequence cut to its ten biggest months is
no longer a sequence — yet the sentence still read ", top 10" and the top-N
picker still accepted a limit. The clause promised a cut the result never had.
This makes the sentence and the picker agree with the engine.

## Scope
Covers:
- A `top_n_suppressed(state)` helper mirroring the backend predicate, used by
  both the sentence and the config zone so they cannot drift.
- The sentence's limit clause reads "all periods" when suppressed.
- The top-N picker slot is greyed out and inert when suppressed.
- i18n key `reports.sentence_all_periods` in `en.json` and `pl.json`.
- BDD `KAL-RPT-011` + unit and e2e coverage.

Not in scope:
- The backend `_limit` logic itself (already correct — this only mirrors it).
- Pivot reports: their `top_n` is applied in `_rows_to_pivot._cut_rows`
  regardless of a trend column, so the limit stays live there.
- Any restyle of the config zone beyond the one disabled-slot state.

## Acceptance criteria
- `uv run pytest tests/unit/views/test_reports_sentence.py -q`
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KAL-RPT-011" docs/bdd.md`

## Touchpoints
- `src/kaleta/views/reports/sentence.py` — `top_n_suppressed`, `top_n_label`
- `src/kaleta/views/reports/config_zone.py` — `_slot(disabled=…)`, top-N guard
- `src/kaleta/views/theme.py` — `SENTENCE_SLOT_DISABLED` + `.k-slot--disabled`
- `src/kaleta/i18n/locales/{en,pl}.json` — `reports.sentence_all_periods`
- `docs/bdd.md` — `KAL-RPT-011`
- `tests/unit/views/test_reports_sentence.py`, `tests/e2e/test_reports_builder.py`

## Implementation notes
- **Exact backend suppression predicate.**
  `SavedReportService._limit` (`src/kaleta/services/saved_report_service.py:334-347`)
  returns `None` (no SQL `LIMIT`) when
  `any(column in TREND_COLUMNS for column in config.active_columns())`, where
  `TREND_COLUMNS = {"change", "moving_avg"}` (`:61`). `_limit` is consulted
  **only on the one-dimensional path** — the `else` branches of
  `_execute_on_transactions` (`:393-394`) and `_execute_on_flows` (`:449-450`),
  i.e. when `config.series is None`. On a pivot (`series is not None`) the cut
  happens in `_rows_to_pivot._cut_rows` (`:580-593`) and a trend column does
  **not** spare it.
  `ReportConfig.active_columns()` (`:99-111`) already drops `change`/`moving_avg`
  unless `trend_axis in {month, year}`, and for a one-dimensional report
  `trend_axis == dimension` (`:91-97`). So the net predicate the view mirrors is:
  **`series is None` AND the active columns include a trend column** — which
  for a one-dimensional report means `dimension in {month, year}` AND a
  `change`/`moving_avg` column is on.
- The view's `top_n_suppressed` reuses `sentence.active_columns(state)`, which
  itself delegates to `column_unavailable_reason` -> `ReportConfig.active_columns`,
  so the picker and the service cannot grey out a different set.
- `top_n_suppressed` ignores the `top_n` value on purpose: even a non-zero
  limit is ignored by the engine on a trend report, so "all periods" is the
  honest reading and the picker must be inert regardless of the current value.
