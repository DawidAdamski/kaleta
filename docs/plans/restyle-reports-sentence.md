---
plan_id: restyle-reports-sentence
title: Restyle — Report builder as a clickable sentence with the chart first (artboard 3e)
area: reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md#reports
---

# Restyle — Report builder as a clickable sentence, chart first

## Intent

The report builder (`views/reports/`) puts two drag-and-drop drop zones
and a tall filter panel above a chart that ends up second-class.
Artboard `3e` turns the configuration into a **readable sentence** you
can click through — *Show [Sum of amount] grouped by [Category] for
[expenses] over [this year], top [10].* — so the query is legible before
you run it. Fields still drag from the left rail into the sentence; the
chart takes the space the filter panel used to. The handoff README does
not describe `3e` in prose; the artboard on the canvas is the spec.

Depends on `restyle-theme-tokens`.

## Scope

- **Left rail** (`palette_zone` / `saved_section`): three quiet groups
  with eyebrow labels — *Group by* (the seven `DIMENSIONS`), *Measure*
  (three `METRICS`), *Saved* (saved reports as plain rows). Items keep
  `draggable` and `on_dragstart`; rail width ~220px, ground background,
  no card.
- **Sentence** (`config_zone.py` rewrite): one line of 15px Libre
  Franklin with five inline **slots**, each a `k-filter-chip`-style
  control with `expand_more`: measure (`metric`), dimension
  (`dimension`), transaction types (`transaction_types`, multi), date
  preset (`date_preset`, with from/to inputs when `custom`), `top_n`.
  Clicking a slot opens a `ui.menu` with the same options the current
  controls offer; dropping a rail item on the measure / dimension slot
  sets it (`drop_dimension` / `drop_metric` unchanged). Below the
  sentence: chart-type segmented control (`CHART_TYPES`) and the
  account / category filters as chips (`2 accounts ×`,
  `+ Filter categories`), same state keys.
- **Header row**: `Unsaved report · N transactions in scope` (or the
  saved report's name) at left — N comes from the last result's row
  count if the service exposes it, else omitted; `Export CSV` and
  `Save report` at right (existing handlers).
- **Chart zone** (`chart_zone.py`): full width under the sentence;
  title sentence in ink ("Expenses by category, January – September
  2026" built from the state), total at right (`k-amount`), palette
  from `chart_utils.CHART_PALETTE`; bar chart as horizontal bars with
  value + share % labels as in the artboard (`table` type unchanged).
- Run behaviour: keep the existing trigger (Run button or auto-run —
  whichever `page.py` does today); the sentence edits update state
  exactly as the old controls did.
- BDD: add a Feature "Report Builder" only if none exists (there is no
  `KAL-RPT` today — check first); `KAL-RPT-001` "the builder sentence
  reflects the state and round-trips a saved report" (@automated, e2e).

Out of scope: report engine / new dimensions or metrics; saved-report
storage; canned reports (`reports_canned/`); Money Flow.

## Acceptance criteria

- `uv run pytest tests/e2e/test_money_flow.py -q`
- `grep -q "k-filter-chip" src/kaleta/views/reports/config_zone.py`
- `test "$(grep -c 'drop_here' src/kaleta/views/reports/config_zone.py)" = 0`
- `grep -q "KAL-RPT-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data: the page opens with the sentence *Show Sum of
  amount grouped by Category for expenses over this year, top 10.*;
  clicking *Category* and choosing *Account* re-runs with accounts;
  dragging *Count* onto the measure slot works; chart fills the width
  with a title and total; compare to artboard `3e` in light and dark.

## Touchpoints

- `src/kaleta/views/reports/config_zone.py` (rewrite), `page.py`,
  `chart_zone.py`, `saved_section.py`, `palette.py`, `constants.py`
- `src/kaleta/views/chart_utils.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
  (`reports.sentence_show`, `reports.sentence_grouped_by`,
  `reports.sentence_for`, `reports.sentence_over`, `reports.sentence_top`,
  `reports.unsaved`, `reports.in_scope`, `reports.filter_categories`)
- `docs/bdd.md`, new `tests/e2e/test_reports_builder.py`

## Open questions

1. Polish sentence grammar — the slots reorder poorly in PL ("Pokaż
   [sumę] według [kategorii] dla [wydatków] za [ten rok]"). Default:
   **keep slot order fixed for both locales** and phrase the PL
   connectors so the fixed order reads naturally; no per-locale
   reordering logic.
2. Keep the drop-zone affordance at all? Default: **yes** — the measure
   and dimension slots accept drops (dashed outline while dragging);
   the rail rows also set the slot on click, which is the primary path.

## Implementation notes

_Filled in as work progresses._
