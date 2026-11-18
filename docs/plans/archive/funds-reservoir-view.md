---
plan_id: funds-reservoir-view
title: Funds — reservoir ("jeziorka") visualisation of accounts and reserve funds
area: wizard
effort: large
status: archived
archived_at: 2026-11-18
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Funds — reservoir ("jeziorka") visualisation

## Intent

Sibling to [`reports-money-flow`](reports-money-flow.md), which answers
*"gdzie kończą się moje pieniądze w tym miesiącu?"* with a Sankey. This
plan answers the other half of the same intuition: *"ile wody stoi w
którym zbiorniku i czy poziom rośnie?"* — accounts and reserve funds
drawn as filled reservoirs rather than progress bars, with the streams
between them showing where the water comes from.

It is deliberately a **second** plan. The Sankey carries the analytic
weight and ships on stock ECharts; the reservoir view is the
brand-distinctive layer and needs custom rendering, so it must not
block the useful half.

## Current behaviour (code facts)

- `views/safety_funds.py` (480 LOC) renders each `ReserveFund` as a card
  with a `ui.linear_progress` bar and a percentage label
  (`_render_fund_card`, line 338). `_progress_color()` maps the
  percentage to a Quasar colour token.
- `ReserveFundService.list_with_progress()` already returns
  `ReserveFundWithProgress` — current balance, target, and progress
  fraction — so **the data layer for this view already exists**; the
  work is rendering, not aggregation.
- `ReserveFund.backing_mode` is `account` in practice
  (`envelope` is reserved and not offered in the v1 UI), so a
  reservoir's level is the backing account's balance.
- **No liquid-fill capability**: the ECharts build bundled with NiceGUI
  3.14 contains `sankey`, `themeRiver`, `sunburst`, `treemap` but
  **not** `liquidFill` (verified in
  `nicegui/elements/echart/dist/index-DD0x1K46.js`). A literal water
  rendering must therefore be hand-built — inline SVG (a clipped fill
  rect plus one or two animated wave paths) inside a NiceGUI element, or
  an ECharts `custom` series. Inline SVG is the lower-risk option: no
  chart library semantics to fight, and it themes with CSS variables.

## Scope

- **Reservoir component** — `views/components/reservoir.py`: an inline
  SVG element taking `(label, current, target, currency)` and rendering
  a container with fill height proportional to progress, an overflow
  state above 100%, and an accessible text fallback (the numbers stay in
  the DOM for screen readers and for Playwright).
  Themed from CSS variables so dark mode needs no second code path.
- **Reservoir layout on `/wizard/safety-funds`** — a view toggle
  (bars ↔ reservoirs) on the existing page rather than a new route. The
  card body swaps; all CRUD dialogs stay untouched.
- **Streams (optional second milestone)** — thin connectors from a
  "monthly surplus" source into each fund, thickness proportional to the
  last N months' average contribution into the backing account. Only if
  the contribution figure can be derived without a new model; otherwise
  cut it and keep static reservoirs.
- **Motion budget** — the wave animation must respect
  `prefers-reduced-motion` and stop when the tab is hidden. A finance
  app that animates constantly reads as a toy.
- **BDD**: `KAL-RSV-001` … `KAL-RSV-003` `@planned` (toggle switches to
  reservoir layout; a fund at 100% shows a full reservoir; an overfunded
  fund shows the overflow state).

### Not in scope

- Replacing the progress bars — the toggle keeps both; bars stay the
  default until the reservoir view earns it.
- Accounts page and net worth (a reservoir per account is the obvious
  next step, but scoping it here doubles the surface).
- Any new model, migration, or aggregation: this plan renders data that
  `ReserveFundService` already returns.
- Canvas/WebGL rendering.

## Acceptance criteria

- `uv run pytest tests/unit/views -q`
- `grep -q "KAL-RSV-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Reservoir fill height matches the percentage shown on the
  bar layout for the same fund, in light and dark mode.
- `[manual]` With `prefers-reduced-motion: reduce` the wave is static.
- `[manual]` A fund with target 0 or no backing account degrades to the
  empty state instead of dividing by zero.

## Touchpoints

- `src/kaleta/views/components/reservoir.py` (new),
  `views/components/__init__.py`
- `src/kaleta/views/safety_funds.py` (layout toggle, `_render_fund_card`)
- `src/kaleta/views/theme.py` (reservoir CSS variables in
  `BASE_CSS` / `DARK_CSS`)
- `src/kaleta/i18n/locales/en.json` + `pl.json`
- `docs/bdd.md` (KAL-RSV-001…003)
- `tests/unit/views/`, `tests/e2e/test_reserve_funds.py`

## Open questions

1. **Does the metaphor survive contact with real numbers?** Two funds
   with wildly different targets look equally "full" as reservoirs —
   percentage, not amount, is what the shape encodes. Mitigation: scale
   reservoir *width* by target amount so both dimensions read.
   Decide before building.
2. **SVG vs. ECharts `custom` series** — SVG is the default choice
   above; revisit only if the streams milestone needs real layout.
3. Should the reservoir layout become the default once shipped, or stay
   an opt-in view? Deferred until it can be looked at with real data.

## Implementation notes

**Open questions resolved (plan defaults where one was given):**

1. *Does the metaphor survive real numbers?* — Took the mitigation the plan
   names: reservoir **width** scales linearly with the fund's target relative
   to the largest target among the active funds on the page
   (`width_ratio()`), with a floor of 35 % (`MIN_WIDTH_RATIO`) so a small
   fund's figure still fits inside its basin. Height encodes the percentage,
   width the size. With no positive target anywhere every reservoir is full
   width.
2. *SVG vs. ECharts `custom`* — Inline SVG (plan default). Streams were not
   built, so there was no reason to revisit.
3. *Default layout* — Stays opt-in (plan default, and "Not in scope:
   replacing the progress bars"). Bars are the default; the layout lives in
   `?layout=reservoirs`, so the choice survives a reload and can be linked.

**Streams milestone: cut.** The plan allows it only "if the contribution
figure can be derived without a new model". A contribution figure needs a
per-account monthly inflow average that `ReserveFundService` does not
return today. Adding one is a new aggregation, which is out of scope ("Any
new model, migration, or aggregation"). The reservoirs are static.

**Design decisions a reviewer should know:**

- `views/components/reservoir.py` keeps the arithmetic (`ReservoirLevel`,
  `width_ratio`) pure and separate from rendering. `Reservoir.svg()` returns
  a string; only `Reservoir.render()` touches NiceGUI. The percentage is
  rounded exactly as the bar layout rounds its label
  (`(current/target).quantize(0.01)`, then `round(×100)`), so the two layouts
  cannot disagree about the same fund (manual criterion 1).
- States: `empty` / `partial` / `full` / `overflow` / `unavailable`.
  `unavailable` is the degraded state for target ≤ 0 or no backing account
  (never set, or deleted so that it is no longer among the user's accounts).
  It draws a dashed empty basin with "—" inside it, and the explanation sits
  as a caption under the SVG, because the sentence is wider than the
  narrowest basin. No division happens on that path.
- Accessibility and testing: the SVG has `role="img"`, an `aria-label` and a
  `<title>` carrying name, current, target, currency and percentage, and the
  figure is SVG `<text>`. `data-state` / `data-percent` / `data-fill` give
  Playwright something stable to assert on. All interpolated text is
  HTML-escaped, which is why `ui.html(..., sanitize=False)` is safe here (the
  sanitizer would strip the SVG).
- Currency comes from the backing account (`Account.currency`), loaded in the
  page's existing `_load`. No service change was needed.
- Theme: three tokens (`--k-reservoir-water/-wave/-basin`) in both `:root`
  and `.body--dark`, so dark mode is the token flip and nothing else. The
  water is a muted slate-blue chosen to sit in the sand palette.
- Motion budget: the wave is a CSS animation that slides a two-period path by
  one period. It is `animation:none` under `prefers-reduced-motion: reduce`
  and `animation-play-state:paused` while `html.k-tab-hidden` is set. That
  class is toggled by a `visibilitychange` listener
  (`RESERVOIR_VISIBILITY_JS`), which is added only when the reservoir layout
  is shown. A screenshot run confirmed the computed `animation-name` goes from
  `k-reservoir-wave` to `none` under emulated reduced motion.
- Only the card body swaps. The header figures, the action buttons, the
  footer (backed-by, survival months, goal pace) and every dialog are shared
  between the two layouts. The emergency month ticks belong to the bar and
  are not drawn on the reservoir.
- Added **KAL-RSV-004** (degraded empty state) beyond the plan's 001–003,
  because the third manual criterion describes user-facing behaviour, and
  Working Agreement §5 asks for a scenario for that.

**Tests:** `tests/unit/views/test_reservoir.py` (level arithmetic, width
scaling, SVG content and escaping, motion-budget CSS, tokens in both modes)
and four e2e tests in `tests/e2e/test_reserve_funds.py`, one per KAL-RSV
scenario.

## Implementation

Landed on 2026-11-18 (PR #458).

| SHA | Author | Date | Message |
|---|---|---|---|
| `266fa90a` | Dawid Adamski | 2026-11-18 | Merge pull request #458 from DawidAdamski/plan/funds-reservoir-view |

**Files changed:**
- docs/bdd.md
- docs/plans/funds-reservoir-view.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/components/reservoir.py
- src/kaleta/views/safety_funds.py
- src/kaleta/views/theme.py
- tests/e2e/test_reserve_funds.py
- tests/unit/views/test_reservoir.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
