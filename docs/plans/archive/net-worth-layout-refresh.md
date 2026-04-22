---
plan_id: net-worth-layout-refresh
title: Net Worth — layout refresh + asset/liability split
area: net-worth
effort: medium
status: archived
archived_at: 2026-04-22
roadmap_ref: ../roadmap.md#net-worth
---

# Net Worth — layout refresh + asset/liability split

## Intent

The Net Worth page today is a single vertical scroll that does not
highlight the one number the user wants at a glance: total net worth,
broken down into assets vs liabilities. Give the page a real dashboard
feel.

## Scope

- Header strip: big "Net Worth = {value}" with delta vs 30 days ago
  and vs start-of-year.
- Two-column split below: Assets (left, green accent) and Liabilities
  (right, red accent). Each column lists its contributing accounts
  sorted by value.
- Trend chart underneath: stacked area of assets vs liabilities over
  time (reuse existing series builder).
- Pinned / extended zone support is OUT OF SCOPE here — that lives on
  the Dashboard.

Out of scope:
- Editing account kind from this page — route user to Accounts.
- Cross-currency aggregation (covered under its own plan, later).

## Acceptance criteria

- Header shows current net worth + both deltas with coloured arrows.
- Assets column lists every account whose kind rolls up to "asset"
  (checking, savings, investment, cash).
- Liabilities column lists every account whose kind rolls up to
  "liability" (credit_card, loan).
- Totals at the bottom of each column match the header breakdown.
- Mobile (≤640px): columns stack vertically.

## Touchpoints

- `src/kaleta/views/net_worth.py` — rewrite layout.
- `src/kaleta/services/net_worth_service.py` — expose
  `assets_total`, `liabilities_total`, `delta_30d`, `delta_ytd`.
- `src/kaleta/i18n/locales/*` — new labels for assets/liabilities
  headers and deltas.

## Open questions

- Should cash-on-hand count as an asset by default? (Yes for v1.)
- Should we show a miniature sparkline per account row, or only the
  rollup chart? v1: rollup only, keep rows quiet.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4317f40` | Dawid | 2026-04-22 | feat: dashboard command center, reports library, forecast presets, and plan-driven features |

**Files changed:**
- src/kaleta/views/net_worth.py
- src/kaleta/services/net_worth_service.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- tests/unit/services/test_net_worth_service.py

**Notes:** Layout refresh delivered with expanded service coverage (asset/liability rollups + deltas). Unit tests in `test_net_worth_service.py` cover the new aggregation methods.
