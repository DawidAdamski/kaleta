---
plan_id: reports-library
title: Reports — library of canned reports
area: reports
effort: medium
status: draft
roadmap_ref: ../roadmap.md#reports
---

# Reports — library of canned reports

## Intent

Users want answers, not chart builders. Ship a library of canned
reports that answer specific questions, each a single click away.

## Scope

Initial report set:
- **Spending by category (month)** — bar chart + table.
- **Spending by merchant (month)** — top 20 payees, horizontal bars.
- **Income vs Expense (6 months)** — grouped bars.
- **Monthly cashflow (12 months)** — area chart + table.
- **Year-to-date summary** — KPI tiles + expense-by-group donut.
- **Largest transactions (last 90 days)** — sortable table, top 50.

Each report:
- Opens in its own sub-route (`/reports/<slug>`).
- Exposes a minimal date-range picker where relevant.
- Exports to CSV (reuse existing export utility).
- Has a one-line description at the top.

Out of scope:
- Ad-hoc chart builder / pivot UI — deferred.
- Saving custom date ranges as named presets.

## Acceptance criteria

- Reports landing page lists the 6 reports with titles + 1-line
  descriptions.
- Each report renders on its own page from live data.
- CSV export downloads a file with the same data the chart is
  rendering.
- i18n: titles, descriptions, axis labels, column headers all
  localised.

## Touchpoints

- `src/kaleta/views/reports.py` — landing + per-report pages (or
  split into submodules if views grow).
- `src/kaleta/services/report_service.py` — one method per report.
- `src/kaleta/schemas/report.py`.
- `src/kaleta/i18n/locales/*`.

## Open questions

- Should the landing page order be user-customisable? Deferred — fix
  the order for v1.
- Chart library: keep current (ECharts via NiceGUI). No change.

## Implementation notes

_(filled as work progresses)_
