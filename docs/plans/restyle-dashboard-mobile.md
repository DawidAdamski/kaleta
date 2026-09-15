---
plan_id: restyle-dashboard-mobile
title: Restyle — phone dashboard: safe-to-spend hero, stacked bands, bottom tab bar (artboard 1f)
area: dashboard
effort: large
status: in-progress
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
- BDD: ~~`KAL-DSH-005`~~ **`KAL-DSH-006`** "safe to spend equals income
  minus committed minus spent" (@automated — `KAL-DSH-005` was taken by
  `restyle-dashboard`, and a unit test cannot claim a scenario) and
  `KAL-NAV-006` "bottom tab bar on narrow viewport" (@automated, e2e
  with a mobile viewport).
- `docs/product/dashboard.md`: new section "Safe to spend" with the
  formula.

Out of scope: desktop `1e` (top-nav, ⌘K); Face ID / biometric anything;
a native app shell; mobile passes for other screens (only `3f` login
has a phone artboard, planned in `restyle-login-split`).

## Acceptance criteria

- `uv run pytest tests/unit/services/test_report_service.py -q`
- `uv run pytest tests/integration/test_safe_to_spend.py -q`
- `uv run pytest tests/e2e/test_navigation.py tests/e2e/test_dashboard_customize.py tests/e2e/test_dashboard_mobile.py -q`
- `grep -q "def safe_to_spend" src/kaleta/services/report_service.py`
- `grep -q "KAL-DSH-006" docs/bdd.md`
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

- **Open question 1 — committed.** Default taken: unposted planned
  occurrences due between today and month end, plus projected
  subscription charges in the same window. Expenses only — planned
  *income* is never promised money, and counting it would let a hero
  say you can spend a salary that has not arrived. The two
  de-duplications are not the same: a planned occurrence knows which
  transaction posted it (`exclude_posted`), whereas no transaction
  carries a subscription id, so a subscription charge can only be
  assumed paid once its date is behind us — which is also why the
  window starts at today and not at the 1st. A charge landing on the
  same day for the same amount as a planned occurrence is counted once;
  two *planned* items of the same amount on one day are still two
  payments, and there is a test saying so.

- **Open question 2 — the hero on desktop.** Default taken: registered,
  selectable in Customize, absent from `DEFAULT_WIDGETS`. That left a
  hole — the phone reads the same stored layout, so a hero nobody has
  enabled would never appear on the phone either. `mobile_layout()`
  prepends it when the stored layout does not already carry it, which
  keeps it an ordinary banded widget and means it cannot appear twice
  for someone who did switch it on.

- **Open question 3 — the breakpoint, and how it is detected.** Default
  taken: 768px, measured server-side. The page awaits the socket and
  reads `window.innerWidth`, then builds one tree. A client that never
  connects gets the desktop grid. The consequence, accepted: the layout
  is chosen when the page is built, so dragging a desktop window below
  768px does not turn it into a phone until the next load. Rendering
  both trees would have run every widget's queries twice on the device
  least able to pay for it.

- **`safe_to_spend` takes a day, not a month.** Scope writes
  `safe_to_spend(month)`, but `days_left` and "still due" are both
  questions about a *day*: a month argument alone leaves `days_left`
  undefined for every month but the current one. The method takes an
  optional `today` instead — which is also what lets the scenario be
  tested against fixed dates rather than against whatever today is.

- **`KAL-DSH-005` was already taken, and a unit test cannot claim a
  scenario.** Scope asks for `KAL-DSH-005` "@automated, unit". That id
  belongs to `restyle-dashboard`'s merged-cards scenario, so the new one
  is `KAL-DSH-006` — and the acceptance criterion greping for
  `KAL-DSH-005` would have passed without checking anything. It also
  cannot be a unit test: `scripts/spec_coverage.py` reads only
  `tests/e2e` and `tests/integration`, so the scenario is claimed by
  `tests/integration/test_safe_to_spend.py`, over a real database, with
  every number a literal from the scenario. The unit tests beside it
  cover the edges (the last day of the month, an overspent month,
  planned income, the trailing-average divisor).

- **`KAL-DSH-007`, beyond the two scenarios Scope lists.** The bands and
  the disappearance of the grid are the plan's largest user-facing
  change and Working Agreement §5 asks for a scenario. It asserts the
  three bands, the hero at the head of Now, the four Watch figures, the
  absence of a grid and of an Edit-layout button, and that the page does
  not scroll sideways — and a companion test that a 1360px window still
  gets the grid, because "desktop rendering is untouched" is a claim
  worth a guard now that one code path chooses between two layouts.

- **The Watch band is figures, not widgets.** Scope names net worth,
  predicted 30d, savings rate and YTD net. Three of those four are
  widgets `restyle-dashboard` merged into the month and balance cards
  and marked `legacy` — kept alive only so an old stored layout still
  renders — so there was nothing left to band. The band reads them from
  the services directly and draws them as plain type on the ground,
  which is what the artboard shows anyway. `bands_for_layout` drops
  legacy widgets rather than banding them: the phone layout is new and
  starts without that debt, and three of the four figures they carried
  are in the Watch band already.

- **The drawer was opening itself over the phone.** `page_layout` built
  it with `value=True`, which below Quasar's breakpoint means an overlay
  covering the page you just asked for. Dropping the argument lets
  NiceGUI set `show-if-above`, so the drawer opens on a desktop and
  waits behind "More" on a phone. This is a one-line change in the file
  the tab bar lives in, and the tab bar is unusable without it.

- **The tab bar has its own breakpoint.** `md:hidden` leaves which of
  two utilities wins to stylesheet order, which is how the auth panel in
  `restyle-login-split` came to be invisible at every width. `.k-tabbar`
  declares `display:none` and a `@media (max-width:767.98px)` rule
  instead. Checked in a browser at 390×844 (five 78×60 tabs flush to the
  foot of the viewport, no horizontal scroll) and at 1360×900 (bar gone,
  spacer 0px high, grid intact).

- **There is no quick-add dialog to call into.** Scope says the centre
  button "opens the quick-add dialog already used by `quick_actions`".
  `quick_actions` has no dialog — it navigates to `/transactions`. The
  dialog belongs to the transactions page and is opened on arrival by
  `?new=1`, which is exactly how the global Alt+N shortcut reaches it
  from another page. The tab uses the same route.

- **The Needs-attention banner could not be read at 390px.** Its row was
  `no-wrap` with a `shrink-0` button, so the message column collapsed to
  one word per line beside a button that would not give up any width.
  Flex items shrink before their row wraps, so removing `no-wrap` alone
  changed nothing; the column needed a `min-w-[180px]` floor. On a
  desktop everything still fits on one line, so nothing changes there.
  Two class changes in a widget this plan's Now band names — the chore
  rule covers it.

- **`--k-neutral-bar` was defined and unused.** The token has sat in
  `:root` since the theme pass with no reader; the spent segment is its
  first. It has no dark override and does not need one — it is a warm
  mid grey that reads on both grounds.

- **Stacking:** branched from `plan/restyle-login-split`, which is itself
  unmerged. Open the PR with `--base plan/restyle-login-split`; it must
  merge after every branch below it.
