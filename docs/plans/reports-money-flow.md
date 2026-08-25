---
plan_id: reports-money-flow
title: Reports — money flow diagram (Sankey)
area: reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md#reports
---

# Reports — money flow diagram (Sankey)

## Intent

Kaleta can already say *how much* landed in each bucket — income
statement, cash flow, spending by category — but every one of those
views is a list or a bar chart. None of them shows the money **moving**:
which inflows feed which outflows, and how much of the month actually
survives to savings. The one question a budgeting app should answer at a
glance — *"gdzie kończy się moja wypłata?"* — currently requires reading
three reports and doing arithmetic in one's head.

A Sankey diagram answers it in one picture: sources on the left, a
single budget pool in the middle, sinks on the right, link thickness
proportional to złoty. The water metaphor the user reached for
(*jeziorka, stawy*) survives in the **language and colour** of this view
(dopływy / odpływy / nadwyżka), while the geometry stays a flow graph —
see [Open questions](#open-questions) and the follow-up plan
[`funds-reservoir-view`](funds-reservoir-view.md) for the literal
reservoir rendering.

## Current behaviour (code facts)

- `views/reports_canned/cash_flow.py` renders inflows and outflows as
  two independent bar series on one category axis. Nothing connects a
  source to a sink; the eye cannot trace a złoty through the month.
- `ReportService._sum_by_category()` (`report_service.py:733`) is the
  shared aggregation: it selects over `categorised_flows_selectable()`
  (so splits are already attributed per line), left-joins `Category`,
  filters `is_internal_transfer == False`, and — when no explicit type is
  requested — keeps only `INCOME` and `EXPENSE`, dropping `TRANSFER`
  outright. Uncategorised rows survive as a `NULL` name bucket.
- Nothing in the codebase produces graph (node/link) shaped data.
  `views/reports/constants.py:CHART_TYPES` offers `bar, line, pie,
  donut, table` only, and `saved_report_service.build_echart_option()`
  assumes a flat `labels`/`values` result.
- **ECharts capability verified**: NiceGUI 3.14 bundles the full ECharts
  build — `sankey`, `themeRiver`, `sunburst` and `treemap` are all
  present in
  `nicegui/elements/echart/dist/index-DD0x1K46.js`. `liquidFill`
  (animated water fill) is **not** — it is a separate plugin, so any
  literal "pond" rendering needs custom SVG, not ECharts.
- Report pages follow a fixed scaffold: `register()` → `ui.page(...)` →
  `page_layout()` → `report_header/month_controls/kpi/export_button`
  from `reports_canned/scaffold.py`, dark mode via
  `chart_utils.apply_dark()`, CSV via `formatters.csv_download()`.
  Registration in `reports_canned/__init__.py`, tile in `catalog.py`.
- `views/transactions/page.py` reads **no query parameters** — there is
  currently no way to deep-link the ledger to a category + period, which
  bounds the drill-through scope below.

## Scope

### Service — `services/money_flow_service.py` (new)

`ReportService` is already 768 LOC; the graph builder gets its own
module and its own dataclasses (views import dataclasses from services,
per the existing report pattern).

- `MoneyFlowNode(id, label, kind)` where `kind ∈ {source, pool, sink,
  surplus, deficit}`; `MoneyFlowLink(source, target, amount)`;
  `MoneyFlow(nodes, links, total_in, total_out, net, period_label)`.
- `MoneyFlowService.build(start, end, *, top_n=12, depth=1)`:
  - Reuses `categorised_flows_selectable()` — split lines are attributed
    to their own category, exactly as in `_sum_by_category`.
  - Excludes `is_internal_transfer` rows and `TransactionType.TRANSFER`,
    matching every other category-based report.
  - Graph shape: `income category → BUDGET pool → expense category`.
    With `depth=2`, expense parents expand into their children
    (`Category.parent_id`), giving a third column.
  - **Node ids are namespaced** (`in:<id>`, `out:<id>`, `pool`). A
    category name may legitimately exist on both the income and expense
    side; ECharts' Sankey layout hangs on a cycle, so shared node ids
    are a correctness bug, not a cosmetic one.
  - **Balancing node** (the part that makes a Sankey honest): income and
    expense rarely match. Surplus becomes a `surplus` sink
    ("Nadwyżka → oszczędności"); a deficit becomes a `deficit` source
    ("Pokryte z oszczędności"). Without it link widths misrepresent the
    pool.
  - **Top-N + rest**: keep the `top_n` largest nodes per side, fold the
    remainder into one "Pozostałe" node. A month with 40 categories is
    unreadable otherwise.
  - Uncategorised rows keep their bucket, labelled from i18n — never
    silently dropped.
  - Empty period returns an empty `MoneyFlow` (no nodes), not an error.

### View — `views/reports_canned/money_flow.py` (new)

- Route `/reports/money-flow`, registered in `reports_canned/__init__.py`
  and added to `catalog.py` (icon `water` / `account_tree`, colour
  `teal-7`).
- Period control: reuse `month_controls()` plus a month ↔ whole-year
  toggle (a Sankey of a single month is often too sparse to be useful).
- Depth toggle (top-level categories / expand subcategories) and a
  top-N select (8 / 12 / 20 / all).
- KPI row above the chart reusing `kpi()`: dopływy, odpływy, nadwyżka —
  so the numbers behind the ribbons stay legible.
- Colours from `chart_utils`: income links `CHART_INCOME`, expense links
  `CHART_EXPENSE`, pool `CHART_TEAL`, gradient along each link; dark mode
  through `apply_dark()`. No new hex literals in the view.
- Tooltip: amount + share of total for both nodes and links.
- CSV export of the edge list (`source, target, amount`) via
  `csv_download`.
- Empty state: `EmptyState` component, not a bare label.

### API

- `GET /api/v1/reports/money-flow?year=&month=&top_n=&depth=` in
  `api/v1/reports.py`, returning a `MoneyFlowResponse` added to
  `schemas/analysis.py` (nodes + links + totals). ORM objects never
  cross the boundary — the service already returns dataclasses.

### Specs and tests

- `docs/bdd.md`, Workflow 6 — Insight: new feature block with
  `KAL-FLW-001` … `KAL-FLW-004` tagged `@planned`:
  001 diagram renders income → budget → expenses for a month;
  002 surplus appears as a savings sink and a deficit as a source;
  003 split transactions land in their own category ribbons;
  004 internal transfers do not appear.
  Retag to `@automated` as the tests below land.
- Unit: `tests/unit/services/test_money_flow_service.py` — balancing
  node both directions, top-N folding, uncategorised bucket, split
  attribution, transfer exclusion, empty period, name collision between
  an income and an expense category.
- Integration: `tests/unit/api/` (or `tests/integration/`, matching the
  existing reports tests) for the new endpoint.
- E2e: extend `tests/e2e/` with a money-flow render check (page loads,
  KPI values match the seeded fixture).

### Not in scope

- **Transfers and an account layer.** Account-to-account movement makes
  the graph cyclic and needs its own design pass; v1 stays on the
  income → pool → expense DAG, consistent with every other
  category-based report.
- **Literal reservoir / pond rendering** — see
  [`funds-reservoir-view`](funds-reservoir-view.md).
- **Drill-through to the ledger.** `views/transactions/page.py` accepts
  no query parameters today; wiring node-click → filtered ledger is a
  separate change to the transactions page.
- Dashboard widget, PNG export, time-animated flows, custom report
  builder integration (`CHART_TYPES` stays as it is).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_money_flow_service.py -q`
- `uv run pytest tests/unit/api -q`
- `grep -q "KAL-FLW-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run lint-imports`
- `bash scripts/verify.sh --e2e`
- `[manual]` A month whose income exceeds expenses shows a surplus
  ribbon into savings; a deficit month shows the reverse. Link widths
  sum to the pool on both sides.
- `[manual]` Dark mode: node labels and ribbons legible, no hardcoded
  light-theme colours.
- `[manual]` A category that exists under both income and expense
  renders as two distinct nodes and the layout does not hang.

## Touchpoints

- `src/kaleta/services/money_flow_service.py` (new),
  `src/kaleta/services/__init__.py` (export)
- `src/kaleta/schemas/analysis.py` (response schema)
- `src/kaleta/api/v1/reports.py` (endpoint)
- `src/kaleta/views/reports_canned/money_flow.py` (new),
  `reports_canned/__init__.py`, `reports_canned/catalog.py`
- `src/kaleta/views/chart_utils.py` (link gradient helper, if shared)
- `src/kaleta/i18n/locales/en.json` + `pl.json`
  (`reports_lib.money_flow*`, `money_flow.*`)
- `docs/bdd.md` (KAL-FLW-001…004)
- `tests/unit/services/`, `tests/unit/api/`, `tests/e2e/`

## Open questions

1. **Metaphor.** Sankey is the analytic engine; how far to push the
   water language in labels and iconography (dopływy / odpływy /
   zbiornik vs. neutral income / expenses / budget)? Default: water
   language in the page copy, neutral terms in the CSV export and API.
2. **Default period.** Month matches the other canned reports, but a
   single month can be sparse. Default: open on the current month with
   a one-click switch to the full year.
3. **Where does the pool label come from?** "Budżet" is the obvious
   choice, but the zero-based philosophy might argue for splitting the
   pool by budget envelope. Deferred — v1 keeps one pool.

## Implementation notes

_(filled in as work progresses)_
