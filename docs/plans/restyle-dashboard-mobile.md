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
  Desktop at 1360px is unchanged from `restyle-dashboard` — in
  particular the month card's three figures are still 26px on one line,
  and no page has gained space at its foot.

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

- **Nothing is assigned to the Watch band.** The first cut sent
  `ytd_summary`, `net_worth_trend` and `savings_rate_trend` there as
  slow-moving things. All three are default widgets, so a default phone
  layout got a YTD card and two trend charts drawn directly under the
  four figures that summarise them — with the year-to-date net said
  twice — which is the opposite of the Scope line "four slow-moving
  figures as plain type on the ground … with no cards". They fall to
  *Month* with everything else, `BAND_OF` maps nothing to `WATCH`, and
  both a unit test and the e2e now assert the band carries no
  `data-widget-id` at all.

- **The Watch band and the month card do repeat two figures, cheaply.**
  `month_card`'s footer already carries the predicted 30-day balance and
  net worth, so on a phone they are read twice. The expensive half —
  fitting Prophet — is not: `forecast_service` already caches the
  forecaster's rows in a module-level cache keyed by account, horizon,
  history and model, so the second call re-runs a couple of queries and
  the post-processing, not the fit. A session-scoped memo was written
  and then reverted as redundant. The visible repetition stands: the
  month card states them as a footnote to the month, the Watch band as
  two of the four figures the artboard names.

- **A subscription billed today is counted twice for one day.** The
  committed window starts at today inclusive, and no transaction carries
  a subscription id, so a charge that billed and posted this morning is
  in `spent` and in `committed`. Starting the window tomorrow instead
  would drop a charge due today that has *not* been paid. For a figure
  whose job is to stop you overspending, being told you have less than
  you do for part of one day is the better of the two errors. Written
  into the method's docstring and into `docs/product/dashboard.md`.

- **An overspent month does not get a negative per-day figure.**
  `-14.29 zł a day` is not a budget. `SafeToSpend.spendable` — which was
  carrying nothing but a unit test — now decides the line: with money
  left it reads `X zł a day`, without it reads `X zł over` in the
  expense tone.

- **The month card was widened to fit a phone, which the Touchpoints did
  not anticipate.** Its three 26px mono figures hung one pixel over the
  edge of a 390px screen, and the plan's own manual criterion asks for
  no horizontal scroll. A mono figure does not shrink with its column,
  so `min-w-0` could not help; the column has a floor and the type is
  smaller below `md`, and both revert above it — verified in a browser
  at 1360px (26px figures, `min-width: 0px`). Same chore-rule reasoning
  as the Needs-attention banner.

- **`_viewport_is_mobile` catches only `TimeoutError`.** That is the one
  failure worth swallowing — nobody answered, so build the desktop grid.
  A blanket catch would have turned any other bug into a phone silently
  served the wrong layout.

- **`_watch_figures` stays in the view.** It reads four services and
  turns each answer into a label and a formatted string; the formatting
  is the whole of it, and there is no rule being applied that a service
  could own. Left as a known nit rather than a new service method with
  one caller.

- **The hero cannot be switched off on a phone.** Customize is still
  offered there (which widgets you want is not a question about width)
  and still lists the safe-to-spend checkbox, but `mobile_layout` puts
  the hero back regardless, so unticking it changes only the desktop
  grid. Hiding the row on a phone would make the same dialog say
  different things on two devices about one stored layout, which is
  worse. `KAL-DSH-007` says it out loud instead — as the case the e2e
  actually checks (the hero is there although Customize has it
  unticked); the other direction is a unit test on `mobile_layout`.

- **The spacer is `display:none` above the breakpoint, not zero-height.**
  The page column is a flex container with a gap, so a zero-height last
  child still added a gap's worth of space to the foot of every desktop
  page — 44px on the dashboard, 24px elsewhere. That is not "desktop
  rendering untouched".

- **One breakpoint, not two that disagree at 768px.** `.k-dash-page`
  switched to phone padding at `max-width:768px` inclusive, while the
  tab bar and the layout choice both put a 768px-wide window (an iPad in
  portrait) on the desktop side. A desktop grid with phone padding is
  neither, so `.k-dash-page` now ends at 767.98px like the rest.

- **The Watch band's forecast needs no guard, and the first one written
  here was a lie.** A `try/except` went in around it on the strength of
  "a Prophet that will not fit should not take the page down", and
  review pointed out that `month_card` — a default widget in the band
  *above* — makes the same call unguarded, so the claim held only for
  layouts without it. Looking properly: `ProphetForecaster.run` already
  swallows a model that will not fit and returns nothing, which arrives
  as `predicted_balance_30d is None` and reads as an em dash. The guard
  was catching something that does not happen and hiding everything
  that does; it is gone. Per-widget error isolation for the dashboard at
  large is the open chore-inbox item it already was.

- **The (date, amount) subscription de-duplication has a known edge, and
  a test.** An unrelated subscription billing 49.99 on the same day as a
  49.99 plan is taken for the same payment and counted once, which
  overstates what is safe to spend. No transaction carries a
  subscription id and a projected charge carries no account, so a date
  and an amount are all the two share. Both halves of the rule are now
  unit-tested, with a comment saying to undo it if the two ever gain a
  real link.

- **The hero says "zł", like the rest of the app.** `fmt_amount` has
  hardcoded the suffix since long before this branch and accounts carry
  a `currency` the dashboard has never read. Making three new strings
  the exception would not make the page right, and making the page right
  is a change across every widget — the chore-inbox line that already
  exists for the thousands separator belongs here too.

- **Every desktop dashboard now waits for the socket.** The layout is
  chosen from a width the browser reports, so nothing below
  `page_layout` ships in the first response any more — on a desktop too.
  The wait is a websocket handshake and one JS round trip on a local
  connection; the 10s/5s figures are the ceilings before the fallback,
  not the cost. Recorded because "desktop rendering is untouched" is
  about what is drawn, not about when.

- **The Watch band's savings rate is the year's, not this month's.**
  Review pointed out that a month three days old has kept whatever
  happened to land in it, which is not a figure you *watch*. It reads
  `ytd_summary().savings_rate_pct` and says so in its label; the month's
  own rate is on the month card's pace bar, where it belongs. One fewer
  service call, too.

- **The month card wraps on a phone and nowhere else.** Measured in a
  browser at 800, 900, 1024, 1100, 1280 and 1360px with six-figure
  amounts: three 26px figures on one line at every one of them, and no
  page scroll. Above `md` the column floor reverts to `min-w-0`, so the
  items shrink exactly as they did before this branch rather than
  wrapping — the change is confined to the phone.

- **A plan posted early still has its subscription twin committed.** The
  de-duplication matches an unposted planned occurrence, so a plan dated
  the 20th that was posted on the 12th leaves the matching subscription
  charge in `committed` until the 20th — counted once in `spent` and
  once in `committed`. The error is on the safe side (the hero shows
  less than is free), which is the same trade the same-day case takes,
  and it disappears the moment the two gain a real link.

- **The tabs are buttons, not links.** An `<a href>` would give
  long-press and open-in-new-tab, at the cost of a full document load on
  every tap — on a phone that is the latency the tab bar exists to
  remove. The active tab carries `aria-current="page"` so the bar still
  says where you are.

- **Stacking:** branched from `plan/restyle-login-split`, which is itself
  unmerged. Open the PR with `--base plan/restyle-login-split`; it must
  merge after every branch below it.
