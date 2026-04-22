---
plan_id: dashboard-command-center
title: Dashboard — Command Center (pinned + extended widgets)
area: dashboard
effort: large
status: archived
archived_at: 2026-04-22
roadmap_ref: ../product/dashboard.md
---

# Dashboard — Command Center

## Intent

Turn the Dashboard into a true command center: a pinned zone the user
sees every time, an extended zone of optional widgets, and a catalog
of reusable widgets that can be added / removed / reordered. The
user decides what "their" dashboard means; the app ships a sensible
default.

## Scope

- Two zones on the page:
  - **Pinned** — always visible at the top; small, dense tiles.
  - **Extended** — scrollable below; larger cards.
- Widget contract: id, title, default_size (sm/md/lg), min/max size,
  `render(ctx)` method returning a self-contained NiceGUI element.
  Widgets are pure views backed by services.
- Widget catalog (v1):
  - Net worth KPI
  - Month-to-date spending vs budget
  - Cashflow sparkline (last 60 days)
  - Recent transactions (top 10)
  - Upcoming planned transactions (next 7 days)
  - Top 3 over-budget categories
  - Subscriptions due this month
- Add/remove/reorder UX: "Customize" button reveals edit mode with
  drag-reorder, pin/unpin, remove, and an "Add widget" picker.
- Persistence: per-user layout in `app.storage.user`, versioned so
  schema changes can migrate forward.
- Default layout shipped for new users.

Out of scope:
- User-authored widgets / plugins.
- Per-widget date-range control — widgets use their own sensible
  default; granular filters come later.

## Acceptance criteria

- Fresh user sees the shipped default layout.
- Customize mode supports: drag-reorder within a zone, move between
  zones, remove, add from catalog.
- Layout survives reload and browser change (stored per user).
- No widget ever crashes the page — rendering errors are caught and
  show a small error placeholder.
- Removing a widget from the catalog in code gracefully ignores any
  orphaned references in a saved layout.

## Touchpoints

- `src/kaleta/views/dashboard.py` — split into zones + customize
  mode.
- New `src/kaleta/views/widgets/` package — one module per widget;
  each exporting a class implementing the contract.
- New `src/kaleta/services/dashboard_service.py` — layout load/save,
  migration between layout versions.
- `src/kaleta/schemas/dashboard.py` — layout schema.
- `src/kaleta/i18n/locales/*` — widget titles and descriptions.

## Open questions

- Drag library — use Quasar's built-in `q-drag` behaviours if NiceGUI
  exposes them; otherwise fall back to button-based move up/down.
- Mobile layout: collapse to single-column, ignore zones, keep order.
- Should layout be stored in the DB (per user) once auth/multi-user
  lands? Defer — `app.storage.user` is fine for single-user app.

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4317f40` | Dawid | 2026-04-22 | feat: dashboard command center, reports library, forecast presets, and plan-driven features |

**Files changed:**
- src/kaleta/views/dashboard.py
- src/kaleta/views/dashboard_widgets.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json

**Notes:** Shipped as a single widget-driven page (16 widgets grouped by size kpi/half/full) with a Customize dialog; layout persists in `app.storage.user`. Dashboard service and separate widgets package from the plan were collapsed into `dashboard_widgets.py`; zone split (pinned vs. extended) was replaced by size-bucket grouping.
