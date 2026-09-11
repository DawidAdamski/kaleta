# Handoff: Kaleta visual restyle ("sand" palette) + dashboard restructure

## Overview

Kaleta today is a NiceGUI/Quasar app with the default teal-on-navy look: `--q-primary:#0d9488`,
Inter, a 300px drawer, and a dashboard that renders 18 equally-weighted widget cards in a
4-column grid. The owner's complaint was that quality is uneven between screens, "mainly
dashboard".

This package covers two separable pieces of work:

1. **A new visual language** — warm sand paper, deep ink, apricot accent, forest/terracotta for
   money in and out, Libre Franklin for UI text, IBM Plex Mono for every number. This is
   mostly a `theme.py` change and applies to every screen at once.
2. **Per-screen layout changes** — eleven screens were redesigned. Each is described below with
   what changed and why. These are independent of each other; ship them one at a time.

Do (1) first. It is the cheapest change with the largest effect, and (2) reads correctly on top
of the old palette too if you'd rather not repaint.

## About the design files

`Kaleta Dashboard.dc.html` in this bundle is a **design reference written in HTML**. It is a
prototype of the intended look — not production code, and not a component library to import.
Every screen in it is static markup with inline styles and hand-drawn SVG charts.

The task is to **recreate these designs inside Kaleta's existing environment**: Python +
NiceGUI + Quasar + Tailwind utility classes, with ECharts for charts, following the patterns
already in `src/kaleta/views/`. Do not attempt to port the HTML. Read the values out of it.

Open the file in a browser. It is a canvas: three sections stacked newest-first, each option
carrying a visible id badge (`1a`, `2b`, `3e` …) that this document refers to.

## Fidelity

**High-fidelity.** Colours, type sizes, weights, letter-spacing, radii and spacing are final and
should be matched. Where this document gives a hex value, use that hex value. The two things
that are *not* final:

- **SVG charts are sketches.** They exist to show composition, axis treatment and colour, not
  data. Rebuild them as ECharts series through `chart_utils.apply_dark`, keeping the palette and
  the axis/legend styling described below.
- **Content is the Polish demo seed** (PKO / mBank / Revolut, ~9 240 zł salary, the eight
  budgeted categories, dates around July and September 2026). Treat it as sample data.

## Design tokens

### Light mode

| Token | Value | Used for |
|---|---|---|
| Page ground | `#F3EFE7` | body background, drawer background |
| Surface / paper | `#FCFAF6` | cards, header bar, table bodies |
| Surface sunken | `#F3EFE7` | inset chips and mini-panels *on* a card |
| Surface warm | `#F6F1E7` | table group separators, selected day cell |
| Ink | `#1C1A15` | primary text, primary button fill, active tick marks |
| Ink secondary | `#4A443A` | body copy, secondary table columns |
| Muted | `#6B6353` | captions, sub-labels, inactive icons |
| Muted strong | `#6E6656` | eyebrow labels, table column headers |
| Disabled | `#B5AB96` | disabled controls only (fails AA — never for text) |
| Hairline | `#EDE7DA` | row dividers inside a card |
| Border | `#E2DBCC` | card edges, input borders, section rules |
| Border strong | `#C9BFA8` | budget-plan grid rules, emphasis borders |
| Accent | `#B4591F` | filled accent surfaces (banners, step markers) |
| Accent text | `#9A4E1F` | links, "Open →", active nav icon |
| Accent light | `#DE7B45` | avatar fill, decorative accents only |
| Income | `#36684D` | positive amounts, under-budget bars |
| Expense | `#A44631` | negative amounts, over-budget bars |
| Warning | `#8A5A12` | at-risk / near-limit state |
| Neutral bar | `#8E8676` | "expected" or committed portions of a bar |

### Dark mode

| Token | Value |
|---|---|
| Page ground | `#171613` |
| Surface | `#201F1A` |
| Surface sunken | `#2A2822` |
| Ink | `#F0EBDF` |
| Ink secondary | `#CFC7B6` |
| Muted | `#A8A08D` |
| Muted strong | `#A19781` |
| Hairline | `#2A2822` |
| Border | `#322F27` |
| Accent | `#E8935B` (ink `#241C13` sits on it) |
| Income | `#6FAF87` |
| Expense | `#DE8672` |
| Warning | `#E3B457` |

Note the dark mode is **warm dark, not navy**. The current `#0a0e17` / `#151922` navy is the
main reason light and dark feel like two different products. See `1c` (light) next to `1d`
(dark) on the canvas.

### Contrast

Every text colour above was measured against the ground it actually sits on — which for amounts
is the page ground `#F3EFE7`, not the card `#FCFAF6`. All body and label text clears WCAG AA
(4.5:1). `#B5AB96` is below AA by design and is reserved for disabled controls. If you introduce
new tints, measure against `#F3EFE7`.

### Typography

Two families, loaded self-hosted alongside the existing `inter-var.woff2`:

- **Libre Franklin** — all UI text. Weights used: 300 (page titles), 400, 500, 600.
- **IBM Plex Mono** — every number, without exception: amounts, dates, percentages, counts,
  IDs, the version string. Always with `font-variant-numeric: tabular-nums` so columns align.

| Role | Spec |
|---|---|
| Page title | Libre Franklin 300, 32px, `letter-spacing:-.02em`, ink |
| Eyebrow (above title) | Libre Franklin 600, 10px, `letter-spacing:.2em`, uppercase, muted strong |
| Card title | Libre Franklin 500, 16–17px, ink |
| Card subtitle | Libre Franklin 400, 12px, muted |
| Section header | Libre Franklin 600, 10px, `letter-spacing:.22em`, uppercase, ink, over a 1px border-bottom |
| Table column header | Libre Franklin 600, 10px, `letter-spacing:.14em`, uppercase, muted strong |
| Table cell | Libre Franklin 400, 13.5px, ink |
| Body copy | Libre Franklin 400, 13–13.5px, `line-height:1.6`, ink secondary |
| Hero figure | IBM Plex Mono 400–500, 54–76px, `letter-spacing:-.035em` to `-.045em` |
| KPI figure | IBM Plex Mono 500, 24–28px |
| Amount in table | IBM Plex Mono 500, 13.5px, tabular-nums |
| Nav item | Libre Franklin 400/600, 13px |

Hero figures split the decimals into muted: `47 218` in ink, `,40` in `#6E6656`.

### Geometry

| Token | Value |
|---|---|
| Card radius | 14px (dashboard), 12px (working screens) |
| Control radius | 8px; pills and chips `999px` |
| Card shadow | `0 1px 2px rgba(28,26,21,.05)` — the only shadow in the system |
| Card padding | 26px 28px (dashboard), 22px 24px (working screens), 18px 20px (KPI) |
| Grid gap | 20px (dashboard), 18–20px (working screens) |
| Page padding | 36px 40px 44px (dashboard), 32px 36px 40px (working screens) |
| Band gap | 44px between dashboard bands, 26–28px between page sections |
| Header height | 60px (down from 64px) |
| Drawer width | 236px expanded, 64px mini |
| Min hit target | 44px (mobile), 34px (desktop icon buttons) |

Dark mode drops card shadows entirely and relies on the surface step.

## Step 1 — the palette, in `views/theme.py`

Everything below lives in one file. No view module needs to change.

1. **`BASE_CSS`** — add `@font-face` for Libre Franklin and IBM Plex Mono next to the existing
   Inter rule; serve the woff2 files from `static/fonts/`. Set the body stack to
   `'Libre Franklin', ui-sans-serif, system-ui, sans-serif` and drop the Inter
   `font-feature-settings` line.

2. **Quasar brand variables** — replace the teal block:

   ```
   --q-primary:#B4591F;   /* was #0d9488 */
   --q-secondary:#6B6353; /* was #64748b */
   --q-accent:#DE7B45;    /* was #14b8a6 */
   --q-positive:#36684D;  /* was #16a34a */
   --q-negative:#A44631;  /* was #dc2626 */
   --q-info:#9A4E1F;
   --q-warning:#8A5A12;
   ```

   Dark mode overrides `--q-primary:#E8935B` and `--q-info:#E8935B`.

3. **Amount tokens** — `AMOUNT_INCOME` / `AMOUNT_EXPENSE` / `AMOUNT_NEUTRAL` currently resolve
   to Tailwind's `text-green-7` / `text-red-7` / `text-slate-500`. Point them at new utility
   classes (`k-amount--in`, `k-amount--out`, `k-amount--neutral`) defined with the hexes above,
   so amounts stop depending on Tailwind's ramp. Add
   `font-variant-numeric:tabular-nums; font-family:'IBM Plex Mono',monospace` to all three —
   this alone fixes the column alignment complaint across every table in the app.

4. **Surfaces** — `_SURFACE` becomes `k-surface w-full rounded-xl bg-white/80` **without** the
   `border border-slate-200/70`; the border is replaced by the 1px shadow. `PAGE_SHELL` moves
   from `bg-slate-50` to the sand ground. `HEADER` and `DRAWER` take paper and ground
   respectively.

5. **`PAGE_TITLE`** — currently `text-3xl font-semibold tracking-tight text-primary`. The title
   should not be brand-coloured; make it `text-[32px] font-light tracking-tight` in ink. Same
   for `SECTION_HEADING` and `DIALOG_TITLE` — 500 weight, ink, not `text-primary`. Accent
   colour is for actions, not for headings.

6. **The `@layer quasar_importants` block** — most of those ~40 `!important` dark-mode overrides
   exist to drag Tailwind's slate/green/red/blue ramps into the navy theme. Once amounts and
   surfaces use named tokens, the majority can be deleted. Work through them; don't port them.

7. **`DARK_CSS`** — swap the navy values for the warm dark table above. The rule *structure*
   (`.body--dark .q-drawer`, `.k-nav-item--active`, the scrollbar rules, the `.q-drawer--mini`
   block) is all still correct and should be kept as-is.

Two new utility classes are needed app-wide, both used by several screens below:

```
.k-pace          /* 7px track, radius 4, background #EDE7DA, position:relative */
.k-pace__fill    /* absolute inset-y-0 left-0, radius 4 */
.k-pace__tick    /* absolute 2px wide, 13px tall, top:-3px, background #1C1A15 */
```

```
.k-filter-chip   /* 6px 12px, radius 999, background #F3EFE7, 12.5px Libre Franklin */
.k-filter-chip--empty  /* same box, transparent, 1px dashed #CFC5AE, muted text */
```

## Step 2 — screens

Ids in brackets are the badges on the canvas. `1a` is the current UI recreated from source and
exists only as the before-picture; do not implement it.

### Dashboard — `views/dashboard.py`, `views/dashboard_widgets/`

Three options were explored, in ascending order of change. **Pick one.**

**`1b` Polish only.** Keeps all 18 widgets, the 4-column grid, drag-and-drop, and the teal
identity. Four changes: (a) `total_balance` spans 2×2 and renders at 52px with a per-account
footer, while the other KPIs shrink to a single 24px line; (b) every figure becomes IBM Plex
Mono tabular; (c) widget titles collapse from a two-line eyebrow + heading pair to one 15px
line; (d) 24px rhythm throughout. Roughly a `theme.py` + `dashboard_widgets/helpers.py` change.
No widget is added or removed.

**`1c` / `1d` Restyle.** Same widget list and same `DEFAULT_WIDGETS` order, new palette, light
and dark. Structural deltas from `1b`: the seven KPI widgets merge into two 2-column cards
(balance-with-accounts, and month in/out/net with a savings-rate bar carrying a target tick);
the wizard "needs attention" widget becomes a full-width accent banner. The drawer loses its
per-item boxes and becomes a quiet index.

**`1e` / `1f` Rethink.** Desktop and mobile. The dashboard stops being a widget wall and answers
one question — *am I on track this month?*

- A **safe-to-spend** hero: `income − committed − spent`, with a 3-segment bar
  (committed `#1C1A15` / spent `#8E8676` / free `#DE7B45`), a per-day figure, and the actual
  running average next to it. This is a new computation; it needs a service method.
- The 18 widgets fold into three bands — **Now** (safe-to-spend + needs-attention + two
  actions), **Month** (cashflow chart, budgets, next 14 days), **Watch** (four slow-moving
  figures as plain type on the ground, no cards).
- The 24-item drawer collapses to 5 top-nav sections (Overview / Money / Plan / Insight / Setup)
  plus a ⌘K command palette for the long tail. `NAV_GROUPS` in `layout.py` already has the
  grouping; this promotes it to the top bar.
- Widget drag-and-drop survives, scoped to the Month band only. `dashboard_widgets/layout.py`
  persistence still applies; the legacy-migration path needs a band assignment per widget.

`1f` is the phone version: same hero, bands stacked, bottom tab bar with a centre add button,
44px minimum targets.

### Transactions — `views/transactions/page.py`, `views/components/`

**`2a`.** The seven `filter_bar.py` filters currently render as full Quasar selects with floating
labels, which takes three rows. Replace with `k-filter-chip`s that **show their value** and only
show the field name when unset: `01.06.2026 → 03.07.2026`, `PKO Konto Główne +2`, `Expense`, then
dashed `+ Category` / `+ Tag`. One row, with `Clear all 3` on the right. Selection state gets its
own warm bar (`#EFE3D6`) with the selected total on the right — that total is new.

Table columns unchanged from `transaction_table.py` (checkbox, date, account, description,
category, type, amount, tags, actions), but: date is `DD.MM` in mono muted, amount is the only
right-aligned column, category is a pill, and the week separator rows carry the group's net.
Pagination gains the existing group-by toggle inline. Split rows show a `call_split` glyph plus
`Split (3)` in place of the category; rows with notes show `sticky_note_2` before the description.

### Budgets → Realization — `views/budgets/realization.py`

**`2b`.** `realization.py` currently ends each row with a coloured status word. Replace with a
**pace bar** (`.k-pace`): fill width = `min(used_pct, 100)`, fill colour = income/warning/expense
by threshold, and a tick at *percent of month elapsed*. At 10% elapsed and 115% spent, Żywność
explains itself with no legend. Two rows carry a one-line explanation under the bar
("Paid in full on the 1st — expected", "284,00 zł planned for the 12th") drawn from planned
transactions — worth adding, it removes most false alarms. The four summary KPIs and the flat/
by-parent toggle stay as they are.

### Budget Plan — `views/budget_plan/grid.py`

**`2c`.** The densest screen in the app, so it gets the opposite treatment from everything else:
**no card, no shadow** — hairlines only, and the paper is the table. Each category becomes two
rows: planned figures in ink, and an `actual` sub-row beneath in 10.5px mono muted, with
over-budget months in expense colour. Empty future months render `—`, never `0`, so the eye
skips them. The current month's column is tinted `#F0E5D4`. The recurring "Month" column stays,
in accent.

Trade-off to be aware of: the per-row `event_note` / `delete_sweep` action buttons move into a
right-click context menu on the row, to buy back the width the 12 month columns need.

### Import — `views/import_view/`

**`2d`.** `step_indicator.py`'s six numbered pills become a progress line: completed steps are
filled ink circles with a check, the current step is a filled accent circle with its number,
future steps are outlined. Labels sit under each node.

The mapping step (`mapping_section.py`) becomes two columns: **CSV sample on the left**
(delimiter/encoding/row count as a mono caption, first four rows in a bordered mini-table with
`1: Data`, `2: Opis` … column headers) and **field pickers on the right**, so you map a column
while looking at its values. Auto-detected fields get a small `auto` badge in income colour —
the current screen can't tell you what it guessed, which is its main weakness. Parse failures
are surfaced here as a warning strip naming the row numbers, rather than only at Preview.

### Forecast — `views/forecast.py`

**`3a`.** The page currently renders empty behind a Run button. **Run the baseline on load** and
demote Run to a re-run; the account/horizon/preset controls move onto the title row. Four KPIs:
balance today, predicted, change, and confidence at the horizon.

Chart is one ECharts instance: solid ink line for actuals, dashed accent for the prediction,
`#EFCDB2` confidence band, dotted muted baseline when a non-baseline preset is active, a dashed
`markLine` at today, and a `markLine` + point per scenario. Two things to get right, because the
prototype got both wrong first: the x-axis must be **linear across history and forecast** (a
category axis over sparse dates will compress history), and the KPI figures must include the
scenario shifts if the chart's line does.

The Prophet-unavailable banner shrinks from a full-width amber `bg-amber-1` row to a footnote
under the chart title, keeping the docs link. Scenario chips keep their add/remove behaviour and
`app.storage.user` persistence.

### Net Worth — `views/net_worth.py`

**`3b`.** The centred hero card becomes a left-aligned headline with the two delta pills inline,
plus a **proportional 3-segment bar** — accounts / physical assets / liabilities — so the shape
of the balance sheet reads before any table. Physical assets move up beside the hero as a
compact table with inline edit affordances; the add-asset row stays.

Keep `_chart`'s deliberate stacking (liabilities plotted on top of assets, so the top edge is
both sides combined) — but **label it**, because unlabelled it reads as if the upper line were
net worth. The axis must run to 0 or the 21k liability band is off-scale. Drop the 0.35-opacity
area fills to ~0.22; they were the least legible thing on the page. Annotate each series with
its end value.

Assets and liabilities keep the two-column split; the footnote about personal loans not being
counted is new and worth keeping.

### Payment Calendar — `views/payment_calendar.py`

**`3c`.** `_draw_day_cell` currently stacks an inflow line, an outflow line and a count badge in
every cell — 31 cells × 3 numbers. Replace with **the day's net plus a row of small dots**, one
per item, coloured by direction. Totals live in the month KPI row and in the day sheet, where
there's room for them.

Overdue items move out of the day-1 cell into a **pinned strip** above the grid, listing each
overdue item with its age and a `Post both` action — that's where a user looks for them. Today's
cell gets a 2px ink border and a `Today` label; the selected day gets the warm surface. The day
side-sheet keeps its structure (totals, planned, subscription charges, quick-add) with the
existing post-occurrence buttons.

### Financial Wizard — `views/wizard.py`

**`3d`.** The page currently paints six section cards with saturated header bars in six different
hues (`blue-6`, `indigo-7`, `green-7`, `orange-7`, `purple-7`, `cyan-7`) and thirteen steps, of
which eight are "Coming soon". Drop `_SECTION_COLORS` entirely.

New order: hero → **mentor suggestion** as a single accent-bordered card → **Setup** as four
compact done-cards (collapsed by default once `all_done`, as now) → **Routines** as one plain
two-column index. Rank by readiness, not by section: the five steps with routes render in ink
with an `Open` action, the eight without render muted with a single quiet label. The prototype
says "Not built" rather than "Coming soon" — a wording call for a public repo, revert if you
disagree.

### Login — `views/login.py`, `views/auth_common.py`

**`3f`.** A single-user self-hosted app doesn't need a card floating in a centred viewport.
`auth_page_shell` becomes a two-panel split: form on the sand ground at left with the wordmark
above it, and an ink panel at right carrying one line of copy and three counts pulled from the
database. The rate-limit / failed-login message gets a **reserved slot** so it doesn't push the
button down when it appears — that's the actual usability bug on the current page.

Mobile version alongside, 48px fields and buttons. Note: the phone mock shows a **Face ID**
button that does not exist in the codebase — treat as a proposal, not a requirement.

## Interactions & behaviour

Nothing in this redesign changes app behaviour except where called out. Specifically:

- Widget drag-and-drop, layout persistence and legacy migration (`dashboard_widgets/layout.py`)
  are unchanged for `1b`/`1c`, and scoped to one band for `1e`.
- Filter, sort, group-by, pagination and bulk-select semantics are unchanged; only their
  presentation changes.
- `app.storage.user` keys (`dark_mode`, `forecast_preset`, `forecast_scenarios`,
  `wizard_onboarding_open`, `wizard_mentor_dismissed`, `sidebar_mini`,
  `payment_calendar_overdue_days`) all keep working.
- Transitions: `transition-colors` on nav and rows, as now. No new animation.
- Hover: rows lift to `#FAF4E9`, nav items to `#FCFAF6`, icon buttons to the sunken surface.

New computations required:

| Screen | Needs |
|---|---|
| `1e` | safe-to-spend (income − committed − spent), committed total, per-day rate, trailing average |
| `2a` | selected-row total; per-group net for separator rows |
| `2b` | percent-of-month-elapsed; per-row planned-payment explanation |
| `3b` | accounts vs physical vs liabilities split for the proportional bar |

## Responsive behaviour

Desktop screens are drawn at 1360px. They are fluid: the 4-column dashboard grid should collapse
4 → 2 → 1, the two-column splits stack, and the drawer becomes an overlay. `2c`'s 12-month grid
is the exception — it scrolls horizontally rather than reflowing.

Mobile is specified for two screens only (`1f` dashboard, `3f` login). The rest need a pass if
mobile matters to you; the tab bar in `1f` is the intended pattern.

## Assets

- **Fonts**: Libre Franklin and IBM Plex Mono (both SIL Open Font License, so AGPL-compatible).
  Self-host as woff2 in `static/fonts/` next to `inter-var.woff2`.
- **Icons**: Material Symbols Outlined — the same set the app already uses. No new icons beyond
  `calculate`, `filter_list`, `call_split`, `sticky_note_2`, `lightbulb`, `fingerprint`.
- **No images.** Every chart in the prototype is hand-drawn SVG standing in for ECharts, and no
  photography or illustration is used anywhere.

## Files

- `Kaleta Dashboard.dc.html` — the whole design. Open in a browser; pan and zoom.
  - **Turn 1** (bottom): dashboard — `1a` current, `1b` polish, `1c`/`1d` restyle light+dark,
    `1e`/`1f` rethink desktop+mobile.
  - **Turn 2** (middle): `2a` Transactions, `2b` Budgets/Realization, `2c` Budget Plan,
    `2d` Import step 3.
  - **Turn 3** (top): `3a` Forecast, `3b` Net Worth, `3c` Payment Calendar,
    `3d` Financial Wizard, `3e` Reports, `3f` Login desktop+mobile.
- `support.js` — runtime for the HTML file. Not part of the design; keep it beside the HTML so
  the file opens.

Source files read while designing, and the ones each screen maps back to:

| Screen | Source |
|---|---|
| Dashboard | `views/dashboard.py`, `views/dashboard_widgets/*` |
| Transactions | `views/transactions/page.py`, `views/components/transaction_table.py`, `views/components/filter_bar.py` |
| Budgets | `views/budgets/page.py`, `overview.py`, `realization.py` |
| Budget Plan | `views/budget_plan/grid.py`, `toolbar.py` |
| Import | `views/import_view/step_indicator.py`, `mapping_section.py` |
| Forecast | `views/forecast.py`, `views/chart_utils.py` |
| Net Worth | `views/net_worth.py` |
| Payment Calendar | `views/payment_calendar.py` |
| Wizard | `views/wizard.py` |
| Reports | `views/reports/config_zone.py`, `constants.py` |
| Login | `views/login.py`, `views/auth_common.py` |
| All | `views/theme.py`, `views/layout.py` |

## Suggested order

1. `theme.py` — palette, fonts, mono amounts. Every screen improves, nothing moves.
2. `2a` filter chips + `2b` pace bars. Highest ratio of perceived quality to effort, and both
   introduce reusable classes.
3. Whichever dashboard option you picked. `1b` is a day; `1e` is a week and needs a service
   method.
4. `2d` import mapping, `3a` forecast-on-load, `3f` login error slot — three real usability
   fixes, independent of each other.
5. `2c`, `3b`, `3c`, `3d`, `3e` — presentation work, any order.
