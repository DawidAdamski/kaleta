---
plan_id: restyle-net-worth
title: Restyle — Net Worth left-aligned hero, proportional bar, labelled stacked chart (artboard 3b)
area: net-worth
effort: small
status: draft
roadmap_ref: ../roadmap.md#net-worth
---

# Restyle — Net Worth hero, proportional bar, labelled chart

## Intent

`views/net_worth.py` centres a hero card and draws a stacked area chart
with 0.35-opacity fills that were the least legible thing on the page.
Artboard `3b` makes the hero a left-aligned headline with the two delta
pills inline, adds a **proportional 3-segment bar** — accounts /
physical assets / liabilities — so the shape of the balance sheet reads
before any table, moves physical assets up beside the hero as a compact
table with inline edit affordances, and **labels** the deliberate
stacking in `_chart` (liabilities on top of assets, top edge = both
combined) so it no longer reads as if the upper line were net worth.
The axis runs to 0; fills drop to ~0.22; each series is annotated with
its end value.

Depends on `restyle-theme-tokens`.

## Scope

- **Hero** (`_header_strip`): left-aligned 54px mono figure, decimals
  muted; `_delta_pill`s inline to the right (month / year), restyled as
  chips using income / expense tokens.
- **Proportional bar**: 3 segments sized by `account assets` /
  `total_physical_assets` / `total_liabilities` from `NetWorthSummary`
  (add an `account_assets` property so the view does not subtract);
  colours ink / neutral bar / expense; legend under the bar with the
  three amounts. Pure helper `balance_sheet_split(summary)` returning
  percentages, unit-tested (zero-total case → hidden bar).
- **Physical assets** section moves beside the hero (2-column ≥ `lg`,
  stacked below); compact table, inline edit / delete icons, the
  add-asset row stays.
- **Chart** (`_chart`): keep the stack; `yAxis.min = 0`; areaStyle
  opacity 0.22 with palette colours (income / expense tokens);
  `legend` shown with i18n names "Assets" / "Liabilities (stacked on
  assets)"; `endLabel` (or a `markPoint` at the last index) with the
  end value per series; axis via `chart_utils.apply_dark`.
- **Footnote** under the assets / liabilities tables: "Personal loans
  you have given are not counted here" (new i18n key), linking to the
  personal-loans page.
- BDD: `KAL-INV-005` "net worth chart labels the stacked liabilities"
  is presentational — use `[manual]` instead of a scenario; add
  `KAL-INV-005` only for the split helper (@automated, unit).

Out of scope: net worth computation, physical asset model, history
generation, the account table columns.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_net_worth_service.py -q`
- `grep -q "balance_sheet_split" src/kaleta/views/net_worth.py`
- `test "$(grep -c '0.35' src/kaleta/views/net_worth.py)" = 0`
- `grep -q "KAL-INV-005" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data: hero left-aligned with inline delta pills; a
  3-segment bar whose widths match the amounts; chart has a legend
  naming the stacking, y-axis starts at 0, both series end-labelled,
  fills visibly lighter than before. Compare to artboard `3b` in light
  and dark.

## Touchpoints

- `src/kaleta/views/net_worth.py`
- `src/kaleta/services/net_worth_service.py` (`account_assets`
  property; split helper may live here)
- `src/kaleta/views/chart_utils.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
  (`net_worth.split_*`, `net_worth.chart_liabilities_stacked`,
  `net_worth.loans_footnote`)
- `docs/bdd.md`, `tests/unit/services/`

## Open questions

1. End-value labels via `endLabel` (ECharts ≥ 5.1, line series) or a
   manual `markPoint`? Default: **`endLabel`** if the bundled ECharts
   supports it (check the NiceGUI version's ECharts), else `markPoint`.

## Implementation notes

_Filled in as work progresses._
