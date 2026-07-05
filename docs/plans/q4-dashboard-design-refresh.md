---
plan_id: q4-dashboard-design-refresh
title: Dashboard design refresh — match the target mockup
area: dashboard
effort: medium
status: in_progress
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Dashboard design refresh — match the target mockup

## Intent

The AI-generated dashboard mockup (`docs/design/dashboard-target.png`)
looks better than the current product — the owner wants the product
to close that gap. This plan treats the mockup as the visual spec for
the dashboard and the shared theme, so the README screenshot can
eventually be a real capture that looks this good.

## Scope

- **Gap analysis first** (recorded in implementation notes before any
  code): side-by-side comparison of the mockup vs the current
  dashboard on seed data — background/surface palette, card corner
  radius and borders, spacing scale, typography (sizes/weights of
  section labels vs values), chart styling (grid lines, series
  colors, legend), sidebar section grouping and iconography, KPI card
  composition (icon chip + label + value).
- **Implement via theme tokens, not per-view styles:** changes land
  in `views/theme.py` (and `chart_utils.py` for ECharts) so every
  page inherits them; per-widget tweaks only where composition
  differs (e.g. KPI icon chip).
- Respect existing rules from `docs/architecture.md` UI Colour
  Schema: semantic colors stay (income green, expense red, transfer
  neutral); every background carries a `dark:` variant; no bare
  Quasar palette classes.
- Light mode must not regress — the mockup is dark-mode; derive the
  light equivalents from the same token changes.
- After the dashboard: apply the same tokens to the remaining pages
  in one sweep (they share components, so most of it is free).
- **Not in scope:** layout/IA changes (widget set and placement stay
  as-is), new widgets, the `ux-audit-feature-categorization` draft
  (separate concern), README screenshot update (manual, after).

## Acceptance criteria

- `./scripts/verify.sh --e2e` green (views change → rule 8).
- No new entries in import-linter ignores; no view file exceeds
  500 LOC.
- `grep -rn "bg-grey-\|text-grey-" src/kaleta/views/` → 0 hits
  (no bare Quasar palette classes introduced).
- `[manual]` Side-by-side: current dashboard vs
  `docs/design/dashboard-target.png` — owner accepts the match.
- `[manual]` Light mode reviewed on dashboard + transactions +
  settings; no unreadable combinations.

## Touchpoints

`src/kaleta/views/theme.py`, `views/chart_utils.py`,
`views/dashboard_widgets/*` (helpers.py primarily),
`views/components/*`, `views/layout.py` (sidebar),
`docs/architecture.md` UI Colour Schema table (update tokens),
`docs/design/dashboard-target.png` (moved from docs/images mockup).

## Open questions

- Font: the mockup appears to use a tighter/different typeface —
  stay on the current stack or add a self-hosted webfont? (Licence
  matters for AGPL distribution; prefer a libre font like Inter.)
- Should the `ux-designer` agent review the gap analysis before
  implementation? (Suggest: yes — cheap second opinion.)

## Implementation notes

### Gap analysis (2026-07-05)

**Reference assets.** Plan touchpoint `docs/design/dashboard-target.png` does not
exist yet. The mockup currently lives at `docs/images/dashboard-dark.png`
(also embedded in README). `screenshot.png` at repo root is a capture of the
*current* product on seed/E2E data. Move/rename the mockup to
`docs/design/dashboard-target.png` as part of implementation prep.

**Method.** Side-by-side review of mockup vs `screenshot.png` and current
tokens/widgets (`theme.py`, `chart_utils.py`, `dashboard_widgets/helpers.py`,
`layout.py`). Layout/IA differences noted for visual context only — plan scope
keeps widget set, placement, and nav structure unchanged.

#### 1. Background / surface palette

| Aspect | Mockup | Current |
|--------|--------|---------|
| Page body | Near-black navy (~#0a–#0f), minimal texture | `slate-900` via `DARK_CSS` (`rgb(15,23,42)`) |
| Card / surface | Slightly elevated dark panel (~#151922), thin border, no visible shadow | `slate-800` (`rgb(30,41,59)`) + `shadow-sm` on cards |
| Border | Very subtle (~#1e2430) | `rgb(51,65,85)` (`slate-700`) — slightly stronger |
| Primary accent | Teal / cyan (nav active, chart line, positive deltas, CTA links) | Quasar default **blue** primary (`text-primary`, `color=primary`) |
| Positive / negative | Emerald green / coral red (soft, not Material-bright) | Semantic greens/reds OK in principle; KPI uses `text-green-700` / `text-red-700`; charts use Material hex (`#4caf50`, `#ef5350`) |

**Gap:** Dark palette is in the right family (slate stack) but mockup is
deeper, flatter (less shadow), and **teal-forward** rather than blue-forward.
Light mode tokens in `architecture.md` (`dark:bg-slate-950`, etc.) are
documented as Tailwind `dark:` variants but **implementation uses
`.body--dark` CSS overrides** in `DARK_CSS` — docs and code should be
reconciled when tokens change.

#### 2. Card corner radius and borders

| Aspect | Mockup | Current |
|--------|--------|---------|
| Corner radius | ~12px (`rounded-xl` feel) | `rounded-2xl` (16px) on `SECTION_CARD`, KPI cards, nav items |
| Shadow | None / imperceptible | `shadow-sm` on all surface cards |
| Border | 1px low-contrast | `border border-slate-200/70` (+ dark override) |

**Gap:** Cards are slightly too round and too “elevated” vs the mockup’s flat
panels. Token change: `rounded-xl`, drop or soften shadow, tighten border
contrast to match mockup.

#### 3. Spacing scale

| Aspect | Mockup | Current |
|--------|--------|---------|
| Page padding | Generous (~24–32px) | `PAGE_CONTAINER`: `p-6 md:p-8` ✓ (close) |
| Grid gap | ~16–20px between widgets | `#dash-grid` `gap: 16px` ✓ |
| Card padding | ~20–24px | `p-5` (20px) ✓ |
| KPI internal | Icon chip + text column, trend row below value | Icon + label + value in one column, no trend row |

**Gap:** Macro spacing is close. KPI **internal** composition needs a second
row (trend/delta) to match mockup — see §8.

#### 4. Typography

| Aspect | Mockup | Current |
|--------|--------|---------|
| Typeface | Tighter, modern sans (Inter-like) | Quasar / system stack (no custom font) |
| Page title | Large bold + subtitle (“Witaj z powrotem…”) | `PAGE_TITLE` `text-3xl font-semibold`; no subtitle |
| Section labels | Tiny uppercase muted (~10–11px) | `SECTION_TITLE` `text-sm` uppercase |
| KPI values | ~28–32px bold | `text-2xl font-semibold` |
| KPI deltas | `text-xs` green/red with arrow + comparison period | Not rendered |

**Gap:** Values could bump one step (`text-3xl`); labels could shrink
(`text-[11px]` — already used in `NAV_GROUP`). Font stack is an **open
question** (Inter vs stay on system). Subtitle/greeting is **out of scope**
(IA unchanged) unless owner wants it later.

#### 5. Chart styling

| Aspect | Mockup (Net Worth Trend) | Current (Cashflow / Net Worth widgets) |
|--------|--------------------------|----------------------------------------|
| Series colour | Teal gradient area + line | Purple `#7e57c2` (net worth), Material green/red/blue (cashflow) |
| Grid lines | Faint horizontal only | `splitLine` `#444444` (dark) via `chart_utils` |
| Legend | Minimal / inline | Bottom legend (cashflow) |
| Chrome | Period pills (1M/3M/6M/1Y/All), summary stat beside chart | Subtitle text only; no period selector |
| Tooltip / axis | Light grey labels on dark | `#e0e0e0` text via `apply_dark()` ✓ |

**Gap:** Centralise chart **series palette** in `chart_utils.py` (teal primary,
semantic income/expense). Grid/split-line colour should move from neutral `#444`
to mockup-aligned slate (~`#1e293b` / `#334155`). Period pills and inline
summary are **IA/feature** items — **out of scope** per plan; style-only pass
covers colours, grid weight, legend placement where widgets already have legends.

#### 6. Sidebar — grouping and iconography

| Aspect | Mockup | Current |
|--------|--------|---------|
| Structure | Flat list (~10 items) | Four collapsible groups + API docs link |
| Branding | Logo “Kaleta.” in sidebar | “Kaleta” in **header** bar |
| Active state | Teal tint / left accent on Dashboard | No distinct active-route styling; icons `text-primary` (blue) |
| Group headers | None (flat) | `NAV_GROUP` uppercase labels + chevron collapse |
| Footer | Dark-mode toggle + user avatar block | Version label; dark toggle and account menu in **header** |
| Icon style | Simple line icons, muted inactive | Material icons, `text-primary` on all nav icons |

**Gap (visual only, IA fixed):** Style grouped nav to *feel* closer — active
item highlight (teal left bar or bg tint), muted inactive icons/text, optional
logo treatment in drawer header — **without** flattening groups or moving
controls that plan marks out of scope. Header vs sidebar chrome split will
remain visibly different from mockup; call out at manual review.

#### 7. KPI card composition

| Element | Mockup | Current (`helpers.kpi_card`) |
|---------|--------|------------------------------|
| Icon chip | Coloured rounded square, ~40px, soft tint bg | `h-11 w-11 rounded-2xl bg-{color}-500/10` ✓ (close) |
| Label | Uppercase muted | `SECTION_TITLE` ✓ |
| Value | Large bold | `text-2xl font-semibold` |
| Trend row | Arrow + absolute delta + % + “vs. &lt;period&gt;” | **Missing** |

**Gap:** Icon chip + label + value structure exists; **trend/delta row is the
main compositional miss**. No `ReportService` helper today for
period-over-period KPI deltas (would need e.g. balance vs 30 days ago, month
net vs prior month, savings rate delta). **Open question for owner:** add
service + KPI trend row (still no new widgets), or style-only refresh without
deltas?

#### 8. Other widget / table styling

- **Recent transactions:** Mockup uses icon-led list rows; product uses
  `ui.table` + `TABLE_SURFACE`. Keep table (IA); improve density, amount
  colours, and header/link styling toward mockup (“View all” as text link).
- **Quick actions:** Mockup has no direct equivalent; flat primary buttons —
  restyle via theme tokens.
- **Bare Quasar greys:** Acceptance requires `grep bg-grey-|text-grey-` → 0 in
  `views/`. Current codebase has many hits (including `helpers.mini_stat`,
  `layout.py`, `dashboard.py` customize dialog). Migration to Tailwind slate
  tokens should happen during this pass, not introduce new greys.

#### 9. Proposed implementation order (after approval)

1. Add/move `docs/design/dashboard-target.png`; update `architecture.md` colour
   table to match new tokens.
2. **`theme.py`:** palette (deeper body, flatter surfaces), radius, shadow,
   spacing tokens, nav active state, KPI card classes, primary accent shift
   (teal via Quasar brand CSS or tokenised Tailwind).
3. **`chart_utils.py`:** series palette constants, grid/axis colours aligned to
   mockup.
4. **`dashboard_widgets/helpers.py`:** KPI chip sizing/radius; optional trend
   row if owner approves data work.
5. **`layout.py`:** sidebar visual polish (active route, icon muted states).
6. Light-mode equivalents for every changed token.
7. Remaining pages inherit via shared tokens (plan § scope).
8. `./scripts/verify.sh --e2e`; manual side-by-side vs mockup.

#### 10. Open questions for owner (before coding)

1. **Font:** Add self-hosted Inter (AGPL-safe) or keep system stack?
2. **KPI trend rows:** Implement deltas (small service addition) or defer?
3. **Primary accent:** Shift global primary from blue → teal (app-wide) or
   dashboard-only? Plan implies theme-wide tokens.
4. **ux-designer review:** Recommended cheap second opinion on this gap list
   before implementation — confirm if desired.
5. **Mockup file path:** OK to move `docs/images/dashboard-dark.png` →
   `docs/design/dashboard-target.png` and fix README link?

**Owner decisions (2026-07-05):** Inter yes; KPI trends yes; teal app-wide yes;
ux-designer review yes; mockup move yes. Implementation in progress.

**UX-designer notes:** Priority — teal/nav active first, KPI rows second, charts
third, card flatness, typography, grey purge, light mode last. Nav active =
4 px left bar + `bg-teal-500/10` (not full pill). KPI trend positive = teal
(not income green); hide unavailable as em-dash preserving row height; savings
rate uses p.p. not %.
