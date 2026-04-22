# Dashboard — Command Center

> Status: product concept, not implemented.
> Parent: [roadmap](../roadmap.md).

## Intent

The dashboard is the user's **financial command center**: the first
screen they open, the one they configure once and rely on daily. Every
user gets a different view because every user tracks different things.

Guiding principles:

- **Configurable.** Users pick which widgets render and in what order.
- **Collapsible.** Any widget can be collapsed to a header-only pill so
  the page stays scannable.
- **Scales from minimal to maximalist.** A user who wants one number on
  the page should be able to hide everything else. A power user who
  wants twelve widgets should be able to fit them.
- **TLDR layout.** Above-the-fold = essentials, instant. Below-the-fold
  = everything else, lazy.

## Layout model

Two zones, one scroll:

1. **Pinned (above the fold).** Always loads synchronously. Intended
   for 1–4 small, glanceable widgets. User chooses what counts as
   "essential" for them.
2. **Extended (below the fold).** Loads lazily as the user scrolls.
   Can hold many widgets, split into optional named sections
   ("Spending", "Savings", "Forecast", …) for navigation.

Both zones use the same widget component and the same config model —
the only difference is eager vs lazy loading.

## Widget contract

Every widget implements:

- **Header:** title, optional icon, menu (refresh, collapse, remove,
  configure).
- **Body:** the visualisation. Can be a KPI number, a chart, a small
  table, or a pinned report.
- **Collapse state:** open / collapsed-to-header.
- **Size hints:** small (1 col) / medium (2 col) / large (full row) on
  the dashboard grid.
- **Config:** JSON blob specific to the widget type.

## Widget catalog (first pass)

Native widgets (built into the dashboard):

- **Total balance** — sum of active accounts.
- **This month: income / expense / net** — three KPI tiles, can be a
  single widget with toggles.
- **Cashflow last N months** — bar + line, N configurable.
- **Top categories this month** — horizontal bar, top 5.
- **Recent transactions** — last N, filterable by account.
- **Budget progress** — donuts for top 3 categories (red/amber/green).
- **Upcoming planned transactions** — next 14 days.
- **Subscription drain** — monthly cost + YoY change (once
  Subscriptions ships).
- **Net worth delta** — month-over-month trend line.
- **Forecast** — 30/60/90-day balance forecast for a chosen account.

Report-backed widgets:

- Any saved report from Reports can be pinned as a widget. The widget
  stores a reference to the report spec (or a snapshot if the user
  wants a frozen view). See *Reports as widgets* in the roadmap.

## Customisation UX

- **"Edit dashboard"** toggle at the top of the page. Entering edit
  mode reveals drag handles, add buttons, and delete icons on widgets.
  Exiting saves.
- **Add widget** opens a catalog modal grouped by category.
- **Reorder** via drag-and-drop (grid snapping by size hint).
- **Per-widget settings** (e.g. "last 6 months" → "last 12 months")
  accessible from the widget header menu, not only from edit mode.

## Persistence

- Dashboard config persists per-user in `app.storage.user`:
  ```json
  {
    "dashboard": {
      "pinned": [
        {"id": "w-1", "type": "kpi_balance", "size": "sm", "config": {...}},
        {"id": "w-2", "type": "kpi_month_net", "size": "sm", "config": {...}}
      ],
      "extended": [
        {"id": "w-3", "type": "cashflow_chart", "size": "lg",
         "collapsed": false, "config": {"months": 6}},
        ...
      ]
    }
  }
  ```
- First-run seeds a sensible default layout so the page isn't empty.

## Open questions

- **Grid system:** 3-column on desktop, 1-col on mobile — confirm
  breakpoints and what happens when a large widget lands on a
  narrow screen.
- **Lazy loading trigger:** IntersectionObserver when the placeholder
  enters viewport? Or a "Load more" button below the pinned zone?
  First feels better; second is simpler to implement.
- **Widget plugin API:** do we let advanced users define custom
  widgets (e.g. a filter + chart template), or is the catalog closed?
- **Mobile:** same grid collapsed to single column, or a fundamentally
  different navigation (tabs per zone)?
- **Theming:** a widget showing red expense numbers should use the
  same red token as Transactions. Tie to the
  "consistent semantic colours" principle in the roadmap.

## Interactions with other modules

- **Reports** — pinning a saved report creates a widget that holds
  the report spec.
- **Budgets** — the Budget-progress widget reads live budget state;
  clicking through opens the full Budgets (realization) view.
- **Forecast** — the Forecast widget delegates to the Forecast
  module; widget config stores account + horizon + model preset.
- **Wizard** — Monthly Readiness section may surface a "Dashboard
  suggestions" step: offer common widget bundles based on user
  behaviour.
