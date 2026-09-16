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

- **Total balance** (`balance_card`) — hero total over the three largest
  accounts that make it up, with the rest collapsed into one "N more"
  tile. Replaces the separate total-balance tile.
- **This month** (`month_card`) — income / expense / net side by side, a
  savings-rate bar ticked at the 20 % target, and, under a hairline, the
  predicted 30-day balance and net worth. Replaces the three month
  tiles, the savings-rate tile, and the net-worth and predicted-30d
  tiles.
- **Needs attention** (`wizard_actions`) — full-width accent banner
  listing the wizard's ranked actions, each with a severity glyph. With
  nothing pending it drops to a quiet "All clear" card.
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

## Safe to spend

The one figure the dashboard leads with (artboard `1f`). A balance
cannot answer "am I on track this month?", because a balance does not
know that the rent leaves on the 28th.

```
free = income − committed − spent
```

- **income** — income posted this month, internal transfers excluded.
- **spent** — expenses posted this month, internal transfers excluded.
- **committed** — what is still due between today and the end of the
  month: unposted planned occurrences (expenses only) plus projected
  subscription charges. Planned occurrences are de-duplicated against
  the transactions that posted them; a subscription charge is assumed
  paid once its date is behind us, because no transaction carries a
  subscription id. A charge that lands on the same day for the same
  amount as a planned occurrence is counted once. The window starts
  today, so a subscription billed *and paid* today is counted in both
  `spent` and `committed` for that day — the alternative drops a charge
  due today that has not been paid, which is the worse error for a
  figure meant to stop you overspending.
- **days_left** — days remaining including today, never below 1.
- **per_day** — `free / days_left`, shown beside the actual mean daily
  spend over the last 30 days so the two can be compared.

Planned *income* is never committed and never counted: money is income
once it has landed. `free` may be negative, and is reported as such —
only the bar clamps it, because a negative width has nowhere to go.

Read by `ReportService.safe_to_spend`; scenario `KAL-DSH-006`.

## Bands

The dashboard reads in bands at every width — the shape the page argues
for, rather than a wall of equal cards:

- **Now** — the safe-to-spend hero, the Needs-attention banner, quick
  actions. On a wide window the hero takes two thirds of the row and the
  rest shares the remaining third; under `lg` they stack.
- **This month** — everything without a band of its own.
- **Watch** — four slow figures as plain type on the ground, no cards
  and no widgets at all (`BAND_OF` maps nothing here): net worth, the
  six-month average savings rate, the 30-day balance and the months the
  emergency funds cover between them
  (`ReserveFundService.emergency_cover` — every fund divides by the same
  trailing monthly spend, so two funds cover the sum of their months).
  Two columns on a phone, four on a desktop. A figure with no answer — no
  emergency fund, no income in the last six months, no recent spending to
  measure cover against — reads "—" rather than inventing a zero. A fund
  with nothing *in* it is a different matter: on a ledger with spending it
  covers 0.0 months, and says so.
- **Latest** — the recent-transactions list, which is a log and not a
  metric, and belongs under everything that is.

Band assignment is `BAND_OF` in `dashboard_widgets/registry.py`. The hero
is an ordinary widget in it, first in `DEFAULT_WIDGETS`: a new profile and
a *Reset widgets* both lead with it, and a profile stored before it
existed gets it by ticking it once in Customize — nothing puts a widget on
the page that its owner has taken off. Band order is fixed — it is the argument the layout is making —
so the stored layout is read for *which* widgets and their order within
a band, never for position. The choice of phone-or-desktop tree is made
once, server-side, from the viewport width the browser reports on
connect: rendering both and hiding one would run every widget's queries
twice, which is what a phone can least afford.

**Dragging is scoped to the Month band** (artboard `1e`). `#dash-grid`
wraps that band alone, and since SortableJS, the resize button and the
layout endpoint all key off that id, they follow it. The hero and the
Latest list are outside it and cannot be dragged away from where the
page needs them. Below the breakpoint there is no grid and no dragging
at all.

## Navigation

Below 768px: a bottom tab bar carrying Home, Ledger, Add, Plan and More
at 44px minimum (artboard `1f`). Add goes to `/transactions?new=1`, the
same route the Alt+N shortcut uses from another page. More opens the
drawer, which keeps the long tail of setup pages that five slots will
never hold.

Above it: a top bar (artboard `1e`) with Dashboard and Financial Wizard
pinned, then five section menus — Capture, Month, Plans, Insight,
Setup — and a "Jump to…" palette on ⌘K / Ctrl+K that filters every route
by name. The drawer is an overlay at every width and stands open at
none: a docked drawer beside the top bar would be the same twenty-four
links twice, and one Quasar considers "desktop" reserves 236px of page
gutter whether or not you can see it.

## Customisation UX

- **"Edit this band"** toggle in the Month band's own header —
  the band whose cards it moves. Entering edit mode reveals drag handles
  and per-widget resize; exiting saves. **Customize** stays in the page
  header: which widgets you want is not a question about a band.
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
- ~~**Mobile:** same grid collapsed to single column, or a fundamentally
  different navigation (tabs per zone)?~~ **Answered** by artboard `1f`:
  three stacked bands and a bottom tab bar — see *Phone layout* above.
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
