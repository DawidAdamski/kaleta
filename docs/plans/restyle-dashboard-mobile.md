---
plan_id: restyle-dashboard-mobile
title: Restyle — phone dashboard: safe-to-spend hero, stacked bands, bottom tab bar (artboard 1f)
area: dashboard
effort: large
status: draft
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle — phone dashboard (safe-to-spend hero, stacked bands, tab bar)

## Intent

Kaleta is a PWA and the 4-column widget grid on a phone is a long scroll
of equal cards. Artboard `1f` shows the phone answering one question
first — *am I on track this month?* — with a **safe-to-spend** hero
(`income − committed − spent`, a 3-segment bar, a per-day figure), the
dashboard content stacked in three bands (Now / Month / Watch), and a
**bottom tab bar** with a centre add button replacing the drawer.
44px minimum hit targets.

`1f` is the phone half of the handoff's `1e` Rethink. Desktop stays on
`restyle-dashboard` (`1c`); this plan adds the phone layout *beside* it
and introduces the safe-to-spend computation the hero needs. The desktop
`1e` rethink (top-nav sections, ⌘K palette, bands on desktop) is
deliberately **not** planned — revisit after living with `1c`.

Depends on `restyle-dashboard` (merged cards, drawer) and
`restyle-theme-tokens`.

## Scope

- **Service**: `ReportService.safe_to_spend(month) -> SafeToSpend`
  (new dataclass next to `KpiPeriodDelta` — `ReportService` already
  backs every month KPI widget): `income` (posted income this month), `committed`
  (planned occurrences still due this month + subscription charges due,
  de-duplicated against already-posted), `spent` (posted expenses),
  `free = income − committed − spent`, `days_left`, `per_day =
  free / days_left`, `trailing_avg_per_day` (mean daily spend over the
  last 30 days). Pure computation on data from existing services;
  unit-tested with fixed dates.
- **Hero widget** `safe_to_spend` (registered like any widget, hidden on
  desktop by default, first on mobile): 54–76px mono figure with muted
  decimals, 3-segment bar (committed `--k-ink`, spent `--k-neutral-bar`,
  free `--k-accent-light`), `X zł / day` next to the actual trailing
  average.
- **Mobile layout** in `dashboard.py`: below the `md` breakpoint render
  the widgets in three stacked bands — *Now*: `safe_to_spend`,
  `wizard_actions` banner, two quick actions; *Month*: `cashflow_chart`,
  `budget_variance_month`, `upcoming_planned` (14 days); *Watch*: four
  slow-moving figures as plain type on the ground (net worth, predicted
  30d, savings rate, YTD net) with no cards. Band assignment lives in a
  `BAND_OF: dict[widget_id, Band]` in `registry.py`; widgets without a
  band assignment fall into *Month*. Desktop rendering is untouched.
- **Bottom tab bar** (`layout.py`, mobile only): five tabs — Home,
  Transactions, **+** (opens the quick-add dialog already used by
  `quick_actions`), Plan (payment calendar), More (opens the drawer as an
  overlay for the long tail). 44px targets, paper surface, hairline top
  border, safe-area padding. Drawer remains available via More.
- Drag-and-drop on mobile: **disabled** (band order is fixed); the
  desktop layout store is not touched by mobile rendering.
- `app.storage.user` keys unchanged.
- i18n: `dashboard.safe_to_spend*`, `dashboard.band_now/month/watch`,
  `nav.tab_*`.
- BDD: `KAL-DSH-005` "safe to spend equals income minus committed minus
  spent" (@automated, unit) and `KAL-NAV-006` "bottom tab bar on narrow
  viewport" (@automated, e2e with a mobile viewport).
- `docs/product/dashboard.md`: new section "Safe to spend" with the
  formula.

Out of scope: desktop `1e` (top-nav, ⌘K); Face ID / biometric anything;
a native app shell; mobile passes for other screens (only `3f` login
has a phone artboard, planned in `restyle-login-split`).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_report_service.py -q`
- `uv run pytest tests/e2e/test_navigation.py tests/e2e/test_dashboard_customize.py -q`
- `grep -q "def safe_to_spend" src/kaleta/services/report_service.py`
- `grep -q "KAL-DSH-005" docs/bdd.md`
- `grep -q "KAL-NAV-006" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` 390×844 viewport on seed data: hero first, bands stacked in
  Now / Month / Watch, bottom tab bar with centre add button, no
  horizontal scroll, every tap target ≥ 44px. Compare to artboard `1f`.
  Desktop at 1360px is unchanged from `restyle-dashboard`.

## Touchpoints

- `src/kaleta/services/report_service.py` (`SafeToSpend` dataclass +
  method; reads `planned_transaction_service` / `subscription_service`)
- `src/kaleta/views/dashboard.py`, `dashboard_widgets/registry.py`,
  new `dashboard_widgets/safe_to_spend.py`
- `src/kaleta/views/layout.py` (tab bar), `theme.py` (`.k-tabbar*`)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/product/dashboard.md`, `docs/bdd.md`
- `tests/unit/services/`, `tests/e2e/`

## Open questions

1. What counts as *committed*? Default: **unposted planned occurrences
   due in the rest of the month + subscription charges not yet posted**;
   credit instalments only if they are planned transactions already.
2. Should the hero also be available on desktop as an optional widget?
   Default: **yes, registered and pickable, not in the desktop default**.
3. Breakpoint for the mobile layout? Default: **< 768px** (Tailwind
   `md`), detected server-side via the existing viewport/user-agent hook
   if one exists, otherwise CSS-only show/hide of two rendered trees is
   *not* acceptable (double queries) — use NiceGUI's
   `ui.context.client` screen width on connect.

## Implementation notes

_Filled in as work progresses._
