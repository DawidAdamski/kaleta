---
plan_id: restyle-dashboard
title: Restyle — Dashboard in the sand palette, merged KPI cards, quiet drawer (artboards 1c/1d)
area: dashboard
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle — Dashboard in the sand palette (1c light / 1d dark)

## Intent

The dashboard renders 18 equally-weighted widget cards in a 4-column
grid; the owner's complaint was "quality is uneven, mainly dashboard".
Of the three dashboard options in the handoff, this plan implements
**`1c` / `1d` Restyle**: same widget list, same `DEFAULT_WIDGETS` order,
same drag-and-drop and layout persistence — but the seven KPI widgets
merge into two 2-column cards, the wizard "needs attention" widget
becomes a full-width accent banner, every figure becomes IBM Plex Mono,
and the drawer stops boxing each item and becomes a quiet index. `1d`
is the same layout in warm dark.

`1e`/`1f` (Rethink: safe-to-spend hero, three bands, top-nav +
command palette) are **not** this plan. The phone layout derived from
`1f` is `restyle-dashboard-mobile`, which depends on this one.

Depends on `restyle-theme-tokens`.

## Scope

- **KPI card A — "Balance"**: one widget `balance_card` replacing
  `total_balance` + `net_worth` + `predicted_30d` visually: hero figure
  (IBM Plex Mono 500, 54px, decimals muted) + per-account footer rows
  (name, institution avatar, `k-amount`), and two small lines for net
  worth and predicted 30d. Spans 2 columns × 2 rows.
- **KPI card B — "This month"**: one widget `month_card` replacing
  `month_income` + `month_expenses` + `month_net` + `savings_rate_kpi`:
  three 24px mono figures (in / out / net) side by side and a savings-rate
  `.k-pace` bar with a target tick (target = existing savings-rate
  target setting if present, else 20 %). Spans 2 columns.
- **Registry & layout migration**: register the two new widgets in
  `registry.py` with `allowed sizes`; keep the seven old widgets
  registered but **hidden from the picker** (`legacy=True`) so stored
  layouts still resolve. `layout.resolve_user_layout` maps a stored
  layout containing any of the seven legacy ids to the two new ids
  (once, idempotent, unit-tested in `test_dashboard_layout.py`).
  `DEFAULT_WIDGETS` starts `balance_card, month_card, wizard_actions, …`.
- **Wizard banner**: `wizard_actions` renders as a full-width accent
  banner (`--k-accent` fill, ink-on-accent text in dark) with the
  actions inline; empty state stays hidden as today.
- **Widget chrome** in `dashboard_widgets/helpers.py`: `section_card`
  title collapses to one 16–17px 500-weight line + optional 12px muted
  subtitle (no eyebrow + heading pair); card padding 26px 28px; radius
  14px; grid gap 20px; band gap 44px; page padding 36px 40px 44px
  (`PAGE_CONTAINER` variant for the dashboard only).
- **Charts** (`cashflow_chart`, `savings_rate_trend`, `net_worth_trend`,
  `budget_variance_month`): series colours from `chart_utils.CHART_PALETTE`
  (ink / accent / income / expense), 1px axis lines in border colour,
  legend text muted, no gradient fills. Composition unchanged.
- **Drawer** (`layout.py` + theme constants): remove per-item rounded
  boxes; group label = eyebrow; item = 13px, active in ink 600 with
  accent icon, hover paper; 236px / 64px mini. This is the drawer for all
  pages, not only the dashboard.
- Responsive: 4 → 2 → 1 columns at the existing breakpoints; the
  2-column KPI cards drop to full width at ≤ 2 columns.
- Update `docs/product/dashboard.md` widget list; update
  `docs/design/screenshot.png` at the end (`[manual]`).
- BDD: `KAL-DSH-004` "legacy KPI layout migrates to merged cards"
  (@automated, unit).

Out of scope: safe-to-spend, bands, top-nav, ⌘K, mobile tab bar
(`restyle-dashboard-mobile`); any widget's data source; edit-mode drag
mechanics (`dashboard-edit-mode-drag`, archived — unchanged).

## Acceptance criteria

- `uv run pytest tests/unit/views/test_dashboard_layout.py -q`
- `uv run pytest tests/e2e/test_dashboard_customize.py tests/e2e/test_wizard_actions_widget.py -q`
- `grep -q "balance_card" src/kaleta/views/dashboard_widgets/registry.py`
- `grep -q "month_card" src/kaleta/views/dashboard_widgets/registry.py`
- `grep -q "KAL-DSH-004" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data, 1360px, light and dark: matches artboards `1c`
  and `1d` — balance hero with per-account footer, month card with
  savings-rate bar and tick, accent wizard banner, quiet drawer, mono
  figures everywhere. Drag-and-drop still reorders and persists; Reset
  layout returns the new default.
- `[manual]` A user profile with the pre-migration stored layout (seven
  KPI widgets) opens without error and shows the two merged cards.

## Touchpoints

- `src/kaleta/views/dashboard.py`
- `src/kaleta/views/dashboard_widgets/registry.py`, `layout.py`,
  `helpers.py`, new `balance_card.py`, `month_card.py`, existing
  `wizard_actions.py`, chart widgets
- `src/kaleta/views/layout.py`, `theme.py` (drawer constants)
- `src/kaleta/views/chart_utils.py` (palette use)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (`dashboard.balance_card`,
  `dashboard.month_card`, savings target label)
- `docs/product/dashboard.md`, `docs/bdd.md`
- `tests/unit/views/test_dashboard_layout.py`, `tests/e2e/`

## Open questions

1. Delete the seven legacy KPI widget modules or keep them
   registered-but-hidden? Default: **keep, hidden**, delete in a later
   cleanup once no stored layouts reference them (log a warning on
   migration so it is observable).
2. Savings-rate target source? Default: **20 % constant** in
   `dashboard_widgets/constants` until a settings field exists.
3. Which of `1c`'s widgets get the `.k-pace` treatment beyond savings
   rate — e.g. `budget_variance_month` bars? Default: **yes**, reuse
   `.k-pace` for its per-category bars (same class, no new CSS).

## Implementation notes

### Read this before reviewing the diff

This branch is **stacked on `plan/restyle-theme-tokens`**, which is not
merged yet — `restyle-dashboard` "Depends on `restyle-theme-tokens`" and
cannot be built without the sand tokens it introduces. So
`git diff $(git merge-base HEAD main)` shows *both* plans: the theme
work (fonts, `theme.py`, `chart_utils.py`, the token sweep across ~20
view files) is the parent branch's, already reviewed and approved on its
own gate, and `docs/plans/restyle-theme-tokens.md` carries its notes.

The 1:1:1 rule holds at the PR, not at the merge-base: this plan's PR is
opened with `--base plan/restyle-theme-tokens`, so it closes one issue
with one branch and one PR whose diff is dashboard-only. To see what this
plan actually changed:

    git diff plan/restyle-theme-tokens...HEAD

### Open questions — decisions taken

1. **Legacy KPI widgets: kept, hidden.** The seven modules stay registered
   with a new `Widget.legacy` flag; `selectable_widgets()` is what the
   Customize picker offers, so they can no longer be added, but a stored
   layout naming one still resolves instead of crashing.
   `migrate_legacy_kpis` logs at WARNING whenever a stored layout still
   names one, which is what makes "no stored layout references them any
   more" observable before the later cleanup deletes them. It is a
   warning rather than an info line precisely because it repeats on every
   load of an untouched profile: the noise *is* the signal that something
   still needs migrating, and it stops the moment the user next drags or
   resizes anything (the POST handler persists the resolved list).
2. **Savings target: 20 % constant**, `dashboard_widgets/constants.py`
   `SAVINGS_RATE_TARGET_PCT`. Artboard `1c` draws its tick at 25 %; that is
   mockup data, not a decision, so the plan's default stands until a
   settings field exists.
3. **`.k-pace` beyond savings rate: yes**, `budget_variance_month` now
   draws one per over-budget category — but *without* a tick. In `1c`
   those bars run full width and only their colour varies, because every
   row shown is already past plan; a tick would mark a target that by
   definition sits behind the fill. Threshold for expense-vs-warning
   colour: **110 % of plan** (`constants.SEVERE_SPENT_PCT`, beside the
   savings target), which reproduces the
   artboard's three rows (115 %, 139 % expense; 106 % warning).

   The percentage it reads is `BudgetVarianceRow.spent_pct`, added for
   this: `variance` and `variance_pct` are signed the *other* way
   (positive = under budget), so a row at 115 % of plan reports −15 %.
   Comparing that against a 110 threshold silently classified every row
   as a warning. `overspend` was added beside it for the same reason —
   the widget had been re-deriving `actual - planned` by hand, with the
   opposite sign to the `variance` property one line away. Both are
   covered by unit tests built from the artboard's three rows.

### Where the artboard overrode the plan text

The plan was written from the artboard's *description*; three details in
`1c`'s markup disagree with its prose, and the artboard won (the manual
acceptance criterion is "matches artboards `1c`/`1d`"):

| Plan text | `1c` markup | Shipped |
|---|---|---|
| Balance card carries "two small lines for net worth and predicted 30d" | those two sit under a hairline in the **month** card | month card |
| Month figures "24px" | `font:500 26px 'IBM Plex Mono'` | 26px |
| Account footer "rows (name, institution avatar, `k-amount`)" | three tiles on `--k-surface-sunken`, radius 10, name over figure, no avatar | tiles |

`month_card` was registered as resizable to `(2,1)` as well. A single
120px row cannot hold an eyebrow, three 26px figures, a pace bar with its
caption, and a hairline footer, so that size is gone — `(2,2)` and
`(4,2)` only.

The page title gained the eyebrow `1c` draws above it — "Jul 2026 · day
3" (`dashboard.period_eyebrow`), which says where in the month the figures
below stand. Not in Scope; it is one line of the artboard's page header
and the merged cards read differently without it.

One widget, one name: the balance card's eyebrow used to read
`dashboard.total_balance` ("Total Balance") while the Customize picker
listed it as "Balance". Both now read `dashboard_widgets.balance_card`,
"Total balance" — which is also the name the scenarios and the product
doc use.

The drawer bullet in Scope ("no per-item boxes, eyebrow group label,
13px items, 236px / 64px mini") is **already delivered** — by the parent
`restyle-theme-tokens` plan, since the drawer is chrome for every page,
not for the dashboard. Nothing in this plan's own diff touches it. See
that plan's Implementation notes for the measurements.

Moving the two slow figures also moved their services: `balance_card`
now needs only `ReportService` + `AccountService`, while `month_card`
pulls `ForecastService` and `NetWorthService`. The 30-day forecast is the
slowest call on the dashboard either way — it did not gain a second
caller, it changed hands. It cannot fail
outright, which is worth stating because merging widgets makes it a fair
question: with no Prophet installed or fewer than 14 days of history the
service returns a result with no prediction rather than raising, and the
footer renders an em dash. (`ForecastUnavailableError` exists in
`exceptions.py` but nothing raises it.) A genuine exception — a database
error, say — still takes the whole page down, because `_render_widget`
isolates no widget from one; that gap predates this plan and is
dashboard-wide, not this card's to close.

### What the wizard banner dropped, and what it kept

Turning a 2x2 card into a 4x1 strip cost information, so it is worth being
explicit about what went:

- **Per-item body text** (`t(item.body_key)`) — a strip has room for one
  line per action, not two. The body is one click away on `/wizard`, and
  the title alone is what the ranking tests read.
- **Section grouping** (`wizard_actions.section_*`) — headers inside a
  single-line banner make no sense. Ranked order survives, which is what
  `KAL-WAC-004` asserts; the five now-unused i18n keys are deleted, along
  with `dashboard_widgets.wizard_actions_sub`.
- **Allowed sizes** changed from `(2,2)/(4,2)` to `(4,1)/(4,2)`: a banner
  that is not full width is not a banner. `KAL-WAC-005` was updated to
  match — it named 2x2, which is no longer offered.

What did **not** go: severity. The coloured dot did, because terracotta on
apricot is unreadable, but each action now leads with an `error` /
`warning` / `info` glyph in `--k-on-accent`. That keeps `KAL-WAC-003`
honest as something a user can see, and carries severity by shape rather
than by colour alone.

The plan says the empty state "stays hidden as today". It never was
hidden — it renders the "All clear" line, which is what `KAL-WAC-001`
asserts. The behaviour is unchanged; only the plan's description of it
was wrong.

### Account tiles

`AccountService.balance_breakdown(limit)` ranks by `abs(balance)` and folds
everything past the third into a count and a sum, which the card renders
as one "N more accounts" tile. Taking the first three of
`AccountService.list()` would have been three *alphabetical* accounts,
and with four or more the tiles would silently fail to add up to the hero
above them. Size, not signed balance: a credit card at −4 000 moves the
total as much as a savings account at +4 000, and folding it into "N more"
would hide the account that explains the hero best. It lives in the
service, not the widget, for the same reason
`current_month_point` does — the card should not be the place that
decides what a balance breakdown means. `KAL-DSH-005` (@manual) covers
what the two cards show.

### Migration

`migrate_legacy_kpis` runs inside `resolve_user_layout`, on both of its
return paths, so every reader of the layout (page render *and* the
`/_dashboard/layout` POST handler) sees the same migrated list. It is a
pure list→list function: each merged card takes the index of the first
legacy entry *mapped to it*, everything else keeps its relative order, and
a widget already present is not added twice — which is what makes a second load a
no-op rather than a duplicate.

Each legacy id maps to the card that absorbed it
(`MERGED_KPI_FOR_LEGACY`) rather than to both: `total_balance` becomes the
balance card, the six month/rate/forecast tiles become the month card. A
user who had removed the balance tile and kept only the month ones gets
the month card back and nothing else — a migration that handed back a
widget someone had deliberately removed would be a worse bug than the one
it fixes.

The stored layout is never rewritten by the migration itself. It is
rewritten the next time the user drags or resizes anything, because the
POST handler validates against the resolved (migrated) list. A profile
that is never touched again migrates on every load, forever, at the cost
of one list comprehension.

### BDD coverage

`KAL-DSH-004` is verified end-to-end in
`tests/e2e/test_dashboard_customize.py`, not by the unit tests: the
scenario is about what a pre-restyle profile *sees*, and
`scripts/spec_coverage.py` only scans `tests/e2e` and `tests/integration`.
The e2e test stores the seven legacy ids through the real
`/_dashboard/layout` endpoint (they are still valid ids at their old
sizes), then loads the dashboard twice. The nine unit tests in
`tests/unit/views/test_dashboard_layout.py` cover the pure function's
edges — partial legacy sets, position, idempotence, default sizes.

Six existing tests in that file had to change fixture widgets (three in
`TestResolveUserLayout`, three in `TestResetLayoutKeepEnabled`): they used
`total_balance` / `month_income` as stand-ins for "some widget", and those
ids now migrate away mid-test. They were re-pointed at `top_merchants` /
`balance_card` / `month_card`, which keeps each test testing its own
subject instead of the migration.

### Chrome and layout

- `DASH_PAGE_CONTAINER` (`.k-dash-page`) is a dashboard-only variant of
  `PAGE_CONTAINER`: 36/40/44 padding and a 44px band gap, dropping to
  20/16/28 and 28px under 768px. `page_layout` takes a `container=`
  keyword; every other page is untouched.
- Responsive needed no new rule. The existing
  `grid-column: span min(var(--cols), 2)` under 768px already takes a
  2-column card to the full width of the 2-column grid.
- The edit-mode chrome (drag handle, resize button, dashed outline,
  focus ring) still carried raw slate/blue rgba literals from before the
  restyle — the one place on the dashboard the sand palette had not
  reached. Retokenised; the drag mechanics are untouched.
- `month_net` lost its `text-green-600` / `text-red-600` pair for the
  `KPI_TREND_*` tokens. It is a legacy widget frozen for deletion, but it
  still renders for anyone whose stored layout names it, and a red that
  the rest of the palette retired is exactly what the restyle is for.
- `mini_stat` took a Quasar hue string (`"green-7"`, `"purple-7"`) and
  rendered `text-slate-500` labels. It now takes a theme amount class and
  renders mono figures, so `ytd_summary` matches the other cards.
- New tokens: `.k-account-chip`, `.k-card-footer`, `AMOUNT_WARNING`
  (`--k-warning` figure, for a small budget overage).

### Two e2e races the suite was hiding

`tests/e2e/` was failing roughly one test per full run — a different one
each time, always passing in isolation. Two real races, both fixed here
because `verify.sh --e2e` cannot be green without them:

- `test_dashboard_customize`: Save re-navigates to `/` itself, and the
  test's own `page.goto("/")` raced it — whichever load lost died with
  `net::ERR_ABORTED`. Now the test waits for the navigation Save starts.
- `test_navigation`: `_ensure_group_expanded` probed `is_visible()` on a
  drawer that was still streaming in, read an expanded group as
  collapsed, and its "expand" click collapsed it. It now waits for the
  group header before probing.
- `test_transactions` (three tests): a split amount was `fill`ed but never
  blurred, so NiceGUI's `change` sync had not fired when "Fill last"
  balanced against the server's model — it wrote a last line that did not
  add up, and Save stayed disabled for good. The amounts now tab out of
  the field, and Save is clicked only once the dialog agrees the lines
  balance.

Neither touches production code; they are test-only and unrelated to the
restyle, so they belong in their own commit.

### Not done

`docs/design/screenshot.png` is still the pre-restyle dashboard. It is
flagged `[manual]` in the acceptance criteria and needs a seeded
1360px capture in both modes, which is the owner's visual pass.
