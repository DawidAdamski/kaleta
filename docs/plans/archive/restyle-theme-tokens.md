---
plan_id: restyle-theme-tokens
title: Restyle — sand palette, fonts and mono amounts in theme.py (handoff step 1)
area: theme
effort: medium
status: archived
archived_at: 2026-09-18
roadmap_ref: ../../roadmap.md#ux
---

# Restyle — sand palette, fonts and mono amounts in `theme.py`

## Intent

Kaleta's screens are uneven in quality and the light/dark modes feel like
two different products (teal-on-white vs teal-on-navy). The design
handoff in `docs/design/restyle/` (`README.md` + `Kaleta Dashboard.dc.html`,
artboards `1c`/`1d`) introduces one visual language — warm sand paper,
deep ink, apricot accent, forest/terracotta for money in and out, Libre
Franklin for UI text and IBM Plex Mono for every number. Almost all of it
lives in `views/theme.py`, so this single plan improves every screen at
once and is the foundation the per-screen `restyle-*` plans build on.

This is **step 1** of the handoff's suggested order. Every other
`restyle-*` plan depends on it.

## Scope

- **Fonts**: add `libre-franklin` (weights 300/400/500/600) and
  `ibm-plex-mono` (400/500) as self-hosted woff2 under
  `src/kaleta/static/fonts/` next to `inter-var.woff2`; add their SIL OFL
  text to `static/fonts/LICENSE.txt`. `@font-face` rules in `BASE_CSS`;
  body stack becomes `'Libre Franklin', ui-sans-serif, system-ui, sans-serif`;
  drop the Inter `font-feature-settings` line. Keep `inter-var.woff2` on
  disk for now (removal is a follow-up once nothing references it).
- **Quasar brand variables** (`:root` in `BASE_CSS`):
  `--q-primary:#B4591F; --q-secondary:#6B6353; --q-accent:#DE7B45;
  --q-positive:#36684D; --q-negative:#A44631; --q-info:#9A4E1F;
  --q-warning:#8A5A12`. Dark (`.body--dark`): `--q-primary:#E8935B;
  --q-info:#E8935B`.
- **Design tokens as CSS custom properties** on `:root` / `.body--dark`
  (`--k-ground`, `--k-surface`, `--k-surface-sunken`, `--k-surface-warm`,
  `--k-ink`, `--k-ink-2`, `--k-muted`, `--k-muted-strong`, `--k-disabled`,
  `--k-hairline`, `--k-border`, `--k-border-strong`, `--k-accent`,
  `--k-accent-text`, `--k-accent-light`, `--k-income`, `--k-expense`,
  `--k-warning`, `--k-neutral-bar`) using exactly the hex values from the
  handoff's "Design tokens" tables (light and dark). Every new `.k-*`
  class below reads these variables so dark mode needs no second copy.
- **Amount tokens**: `AMOUNT_INCOME` / `AMOUNT_EXPENSE` / `AMOUNT_NEUTRAL`
  → `k-amount k-amount--in` / `k-amount k-amount--out` /
  `k-amount k-amount--neutral`. `.k-amount` sets
  `font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums`.
  Also `KPI_TREND_*` → token classes (`k-trend--pos` etc.). Add a
  `MONO = "k-mono"` constant for non-amount numbers (dates, counts,
  percentages, version string) so views can opt in.
- **Surfaces & shell**: `_SURFACE` → `k-surface w-full rounded-xl` with
  background `var(--k-surface)` and the single shadow
  `0 1px 2px rgba(28,26,21,.05)`, **no** `border-slate-200/70`. Dark mode
  drops the shadow. `PAGE_SHELL` → ground; `HEADER` → paper, 60px;
  `DRAWER` → ground; `NAV_ITEM` loses the boxed look (no per-item rounded
  background, active = ink text + accent icon, hover = paper). Drawer width
  236px expanded / 64px mini (`layout.py` `ui.left_drawer(width=…)`).
- **Headings**: `PAGE_TITLE` → `text-[32px] font-light tracking-tight`
  in ink (not `text-primary`); `SECTION_HEADING` / `DIALOG_TITLE` → 500
  weight in ink; `SECTION_TITLE` → eyebrow spec (600, 10px, `.2em`,
  uppercase, muted strong); `BODY_MUTED` → muted token; `TABLE_SURFACE`
  header spec (600, 10px, `.14em`) and hover row `#FAF4E9`.
- **New shared utility classes** (used by later plans, defined here so
  they ship once): `.k-pace`, `.k-pace__fill`, `.k-pace__tick`,
  `.k-filter-chip`, `.k-filter-chip--empty`, `.k-eyebrow`, `.k-mono`.
- **`DARK_CSS`**: replace every navy rgb value with the warm-dark tokens;
  keep the rule *structure* (drawer, `.k-nav-item--active`, scrollbar,
  `.q-drawer--mini` block, menus, dialogs, fields, uploader). Burn down the
  `@layer quasar_importants` block: delete overrides made obsolete by
  tokenised amounts/surfaces; keep only the ones a grep of `src/kaleta/views`
  proves are still referenced (record the survivors in Implementation
  notes with the file that needs each).
- **`chart_utils.apply_dark`**: axis/label/grid colours from the same
  tokens (`chart_text_color`, `chart_grid_color`) and a shared
  `CHART_PALETTE` (ink, accent, income, expense, neutral bar, `#EFCDB2`
  band) so every ECharts instance matches the palette without per-view
  hexes.
- **Settings → Appearance** preview (if `appearance_tab.py` shows swatches)
  updated to the new palette.
- Sweep `src/kaleta/views` for hard-coded Tailwind palette classes that the
  token change makes wrong (`text-primary` on headings, `text-teal-*`,
  `bg-slate-*` used as surfaces) — replace with the theme constants.
  `text-primary` stays legitimate for *actions* (links, "Open →") since
  `--q-primary` is now the accent; it must leave headings and figures. Do
  **not** restructure any page (that is the per-screen plans' job).

Out of scope: any layout change on any screen (`1c`+ dashboard,
`2a`–`3f`); removing `inter-var.woff2`; the ECharts series rebuilds
(per-screen plans); mobile.

## Acceptance criteria

- `test -f src/kaleta/static/fonts/libre-franklin-var.woff2`
- `test -f src/kaleta/static/fonts/ibm-plex-mono-400.woff2`
- `test -f src/kaleta/static/fonts/ibm-plex-mono-500.woff2`
- `grep -q "IBM Plex Mono" src/kaleta/views/theme.py`
- `grep -q "#B4591F" src/kaleta/views/theme.py`
- `grep -q "#171613" src/kaleta/views/theme.py`
- `test "$(grep -c '#0d9488' src/kaleta/views/theme.py)" = 0`
- `test "$(grep -c 'text-green-7' src/kaleta/views/theme.py)" = 0`
- `grep -q "k-pace__tick" src/kaleta/views/theme.py`
- `grep -q "k-filter-chip--empty" src/kaleta/views/theme.py`
- `test "$(grep -c 'text-primary' src/kaleta/views/theme.py)" = 0`
- `uv run pytest tests/unit/views tests/unit/test_pwa.py -q`
- `bash scripts/verify.sh --e2e`
- `[manual]` Light and dark screenshots of Dashboard, Transactions and
  Settings on seed data: sand ground / paper cards in light, warm dark
  (not navy) in dark; all amounts in IBM Plex Mono with aligned decimals;
  page titles in ink not accent. Compare to artboards `1c` / `1d`.
  **Done** — 13 screens shot in both modes at 1360px on the six-year seed;
  see "Seeded visual pass" below for the four defects it caught. Owner
  sign-off against the artboards still welcome.
- `[manual]` Contrast: body and label text on `#F3EFE7` clears 4.5:1
  (spot-check muted `#6B6353` and eyebrow `#6E6656`).
  **Done** — muted 5.18:1, eyebrow 4.95:1; full table below.

## Touchpoints

- `src/kaleta/views/theme.py` (almost everything)
- `src/kaleta/views/layout.py` (drawer width, header height, nav classes)
- `src/kaleta/views/chart_utils.py` (palette, axis colours)
- `src/kaleta/static/fonts/` (+2 woff2, LICENSE.txt)
- `src/kaleta/views/settings/appearance_tab.py` (swatches, if any)
- `src/kaleta/views/**` (mechanical `text-primary` / palette-class sweep)
- `tests/unit/views/test_chart_utils.py` (palette assertions)
- `docs/architecture.md` "UI Colour Schema" section — update the token
  names and the rule "no bare Quasar palette classes" to point at `k-*`
  classes and the CSS variables.
- `docs/design/restyle/README.md` — the spec; do not edit.

## Open questions

1. Variable-font vs static woff2 per weight? Default: **one variable
   woff2 per family** (`libre-franklin-var.woff2`, `ibm-plex-mono-var.woff2`)
   — smallest footprint, matches how Inter is shipped today. If a
   variable build is not available from the upstream release, ship static
   400/500/600 (+300 for Libre Franklin) and name the acceptance files
   accordingly in Implementation notes.
2. Keep the `!important` layer at all? Default: **keep the block but empty
   it down** to survivors proven by grep; delete the layer entirely only
   if zero survive.
3. Does the PWA `manifest.json` `theme_color` follow? Default: **yes**,
   set to `#F3EFE7` (and `background_color` too) — `tests/unit/test_pwa.py`
   may pin the old value; update the test with the new one.

## Implementation notes

### Resolved open questions

1. **Variable vs static woff2.** Split answer, exactly as the default's
   fallback clause allows. *Libre Franklin* ships as one variable file —
   `libre-franklin-var.woff2` (39 KB), subset from upstream
   `google/fonts@ofl/librefranklin/LibreFranklin[wght].ttf` to latin +
   latin-ext (all Polish diacritics verified present) and converted with
   `fonttools[woff]`. Its `wght` axis is 100–900 with default 100, byte-for-byte
   the same axis record Google Fonts serves, so CSS `font-weight` drives it
   normally. *IBM Plex Mono* has **no variable build upstream**: neither
   `google/fonts@ofl/ibmplexmono` (14 statics) nor `@ibm/plex-mono@2.5.0`
   ships one. Per the open question's fallback, it ships as statics for the
   two weights the type scale uses — `ibm-plex-mono-400.woff2` and
   `ibm-plex-mono-500.woff2`, taken verbatim from `@ibm/plex-mono@2.5.0`
   `fonts/complete/woff2/` (full charset, no subsetting needed). The
   acceptance criterion naming `ibm-plex-mono-var.woff2` was replaced by the
   two real filenames, which is what "name the acceptance files accordingly"
   asks for. Both OFL texts are appended to `static/fonts/LICENSE.txt`.
   `inter-var.woff2` stays on disk unreferenced, as the scope requires.
2. **The `!important` layer.** Kept, emptied from ~40 entries down to the
   three survivor groups in the table below (five declarations). Zero-survivor entries were deleted rather than ported.
3. **PWA `theme_color`.** Yes — `manifest.json` `theme_color` and
   `background_color` and the `PWA_HEAD` meta are all `#F3EFE7`;
   `tests/unit/test_pwa.py` pinned the old `#1976d2` in two places and was
   updated to the new literal.

### Changed assertions (rule 4)

Three assertions in existing tests changed value. None was loosened; each
pins behaviour this plan deliberately changed, and all three still assert
an exact literal:

| Test | Was | Now | Why |
|---|---|---|---|
| `test_pwa.py::test_theme_color_meta_present` | `#1976d2` | `#F3EFE7` | Open question 3 — PWA chrome follows the sand ground |
| `test_pwa.py::test_manifest_has_theme_color` | `#1976d2` | `#F3EFE7` | Same |
| `test_chart_utils.py::test_apply_dark_empty_dict_no_error` | `result == {}` | `result == {"color": [six literal hexes]}` | `apply_dark` now seeds the series palette; the test's intent (it must not raise, and must add nothing else) is preserved and tightened to name what it does add |

### `@layer quasar_importants` — survivors

Only classes a grep of `src/kaleta/views` still proves referenced are kept,
and each now resolves through a sand token instead of a navy literal:

| Class | Why it survives |
|---|---|
| `bg-slate-600` / `bg-slate-700` | Inverted chips (`budget_plan/grid.py`, `dashboard_widgets/wizard_actions.py`): ink behind white text in light, which in dark would be near-white on white — the only ramp class whose dark value must *differ* from its light one |
| `bg-green-1` / `bg-blue-1` / `bg-amber-1` | Tints `BASE_CSS` does not remap (`wizard.py`, `budget_plan/grid.py`, `forecast.py`) |
| `text-orange-8` | `budget_plan/helpers.py` (override marker — `2c` retires it) |

The eight other entries this block started with — `text-slate-400/500/600`,
`bg-slate-50/100/200`, `border-slate-300` — turned out to be **redundant**,
not survivors. The unlayered `BASE_CSS` rule for each resolves through a
`var()` that already flips under `.body--dark`, so the `!important` copy
restated the same value. Verified by deleting them and measuring the
computed colour in dark mode on `/transactions`: `text-slate-400` →
`rgb(110,102,86)` (`--k-disabled`), `text-slate-500` → `rgb(168,160,141)`
(`--k-muted`), `text-slate-600` → `rgb(161,151,129)` (`--k-muted-strong`),
`bg-slate-100` → `rgb(42,40,34)` (`--k-surface-sunken`) — every one the
correct dark token with no override present. The block is down from ~40 entries
to five declarations across three survivor groups.

`BASE_CSS` remaps the same ramp for **light** mode, plus two classes that
need no dark override and so do not appear in the table above:
`text-slate-700` (`categories.py` sub-category labels, `payment_calendar.py`)
and `border-slate-200` (grouped with `border-slate-300` onto `--k-border`).

Deleted as unreferenced: `bg-green-2`, `bg-blue-2`, `bg-red-1`, `bg-orange-1`,
`bg-yellow-1`, `bg-teal-1`, `bg-purple-1`, `bg-pink-1`, `text-green-9`,
`text-amber-8/9`, `text-red-8/9`, `text-blue-7/8/9`, `text-orange-7/9`,
`text-teal-600`, and the `.kpi-trend-positive/negative` rules (the classes
they targeted no longer exist — `dashboard_widgets/helpers.py` renders
`KPI_TREND_*`, which are now `.k-trend--*`).

### Seeded visual pass

Ran the app on a six-year seed and shot 13 screens in both modes at 1360px.
Four defects only real data could show, all fixed:

1. **Nav icons overlapped their labels.** Sizing the avatar column to 19px
   left Quasar's 24px glyph overflowing into the text. The column is 31px
   (19px glyph + 12px gutter) with `.k-nav-item .q-icon{font-size:19px}`.
   My earlier "all 25 entries are single-line 44px rows" was measured from
   `getBoundingClientRect` without looking at the render — the heights were
   right and the layout was broken.
2. **Every chart with no explicit colours was still on ECharts' default blue
   ramp** — Budget vs Actual most visibly. `apply_dark` now seeds
   `options.setdefault("color", chart_palette(is_dark))`, which is what the
   scope's "so every ECharts instance matches the palette" asks for and
   finally gives `CHART_PALETTE` its consumer. Per-series `itemStyle` still
   wins, so no chart that names its own colours changed.
3. **Eleven view modules hard-coded Material hexes** (`#1976d2`, `#4caf50`,
   `#ef5350`, `#fb8c00`, `#2e7d32`, `#c62828`, `#009688`, `#bdbdbd`) in
   chart series: `budgets/chart.py`, `net_worth.py`, `forecast.py`,
   `credit_calculator.py` and six `reports_canned/*`. All swapped to the
   token helpers — a colour lookup each, no series restructured. The
   forecast mapping is the handoff's own (ink actuals, accent prediction,
   `#EFCDB2` band, muted baseline). `credit_calculator.py` never called
   `apply_dark` at all, so it also gained `is_dark`; without that, ink on a
   dark card would have been invisible. The eleventh, `budgets/overview.py`,
   hid inside a Vue slot template in *single* quotes and so escaped the first
   scan (which only matched double-quoted hexes); it now binds
   `var(--k-expense)` / `var(--k-income)` straight in the template, which
   flips with the mode without the slot needing `is_dark` at all.
4. **One opacity moved with a colour.** The forecast confidence band went
   from `#fb8c00` at 0.15 to `CHART_BAND` `#EFCDB2` at 0.35. The handoff
   names the band colour but not its alpha; `#EFCDB2` is a pale tint where
   `#fb8c00` was saturated, so holding 0.15 would have made the band
   invisible on paper. 0.35 keeps it at roughly the weight it had. (This is
   unrelated to the `~0.22` the handoff asks of `net_worth.py`'s *area
   fills*, which `3b` owns and this plan left at 0.35.)
5. **Two colours escaped the sweep entirely.** The Net Worth hero built its
   class as `f"text-{color}"`, so grepping for the literal `text-primary`
   never saw an accent-coloured hero figure — now mono ink, or expense when
   negative. And `ui.link` had no rule at all, so the Prophet-unavailable
   link rendered in the browser's default blue; links are now
   `--k-accent-text`.

`tags.py` keeps its `#42A5F5` tag default and `institutions.py` its
`#1976d2` swatch default: both are user-chosen data values, not chrome. `institution_avatar.py`'s `#64748b`
fallback was chrome and moved to the muted token.

### Contrast measurements

Every token against the ground it sits on (`#F3EFE7`) and on paper
(`#FCFAF6`), sRGB relative luminance per WCAG 2.1:

| Token | Light | on ground | on paper | |
|---|---|---|---|---|
| ink | `#1C1A15` | 15.16 | 16.68 | AA |
| ink-2 | `#4A443A` | 8.40 | 9.24 | AA |
| muted | `#6B6353` | **5.18** | 5.70 | AA |
| muted-strong | `#6E6656` | **4.95** | 5.45 | AA |
| income | `#36684D` | 5.64 | 6.21 | AA |
| expense | `#A44631` | 5.23 | 5.76 | AA |
| warning | `#8A5A12` | 5.16 | 5.67 | AA |
| accent-text | `#9A4E1F` | 5.26 | 5.78 | AA |
| accent | `#B4591F` | 4.17 | 4.59 | AA-large only |
| disabled | `#B5AB96` | 1.98 | 2.18 | fails by design |

Dark mode clears AA on every text token (lowest: muted-strong 5.71 on
surface). `#FCFAF6` on the accent fill is 4.59; dark's ink-on-accent is 7.0.

**One thing for the owner to note:** `--k-accent` `#B4591F` is 4.17:1 as
*text* on the ground — below AA for body copy. The handoff assigns it to
filled surfaces and gives `--k-accent-text` `#9A4E1F` (5.26) to links, so
the split is correct by design; but `--q-primary` is `#B4591F` per the
handoff, and Quasar's flat text buttons ("EDIT LAYOUT", "CUSTOMIZE") render
in it. Those sit just under AA. I did not change it — the handoff fixes that
hex — but pointing Quasar's *text* variant at `--k-accent-text` while filled
buttons keep `--q-primary` would close it, and is worth a decision.

### Decisions

- **The Tailwind slate ramp is remapped, not rewritten.** `text-slate-4/5/600`
  alone appears ~250 times across 60 view files; rewriting every call site
  would be a mechanical diff far larger than the rest of this plan and would
  collide with every per-screen `restyle-*` plan still to come. Instead
  `BASE_CSS` redefines the ramp in terms of the sand tokens (light) and the
  `!important` layer does the same for dark. The call sites become correct
  without moving, and each per-screen plan can retire its own as it touches
  them. `bg-slate-*` used as a *surface* is likewise remapped rather than
  hand-edited.
- **`text-green-7` had to leave the views, not just `theme.py`.** The
  acceptance criterion bans the string from `theme.py`, but the class was
  still spelled out in `wizard.py`, so deleting the dark override alone would
  have left "done" ticks unreadable in dark mode. The status colours moved to
  token classes (`k-trend--pos` / `--neg` / `--warn`) in `wizard.py`,
  `safety_funds.py`, `payment_calendar.py`, plus the equivalent `-700` ramp
  spellings in `month_net.py`, `wizard_salary.py` and two `import_view`
  sections. `.k-trend--warn` is the new sibling of the `KPI_TREND_*` set.
- **The `:root` brand block alone never took effect** — and had not for the
  teal palette either. NiceGUI's per-page `ui.colors()` writes its defaults
  (`--q-primary:#5898d4`, …) onto `<body>`, which outranks any `:root` rule
  for every descendant, so `color=primary` buttons and `text-primary` links
  were rendering NiceGUI blue, not the declared brand. Measured in the
  browser: `:root` gave `#B4591F` while `body` gave `#5898d4`. The scope item
  "Quasar brand variables" is only real if they apply, so `theme.QUASAR_BRAND`
  is now the single source and `theme.apply_brand()` pushes it via
  `ui.colors()` from both shells that load `theme_css()` (`layout.page_layout`
  and `auth_common.auth_page_shell`). The `:root` block stays as the static
  fallback, and `test_runtime_brand_matches_the_css_fallback` keeps the two in
  step.
- **Three Quasar primitives paint their own white** and had to be pointed at
  the tokens, or Settings would have stayed white-on-white on sand: `.q-card`
  (every plain `ui.card()`, dialogs included), `.q-tab-panels` / `.q-tab-panel`,
  and the `.q-table` thead/tbody/container chain. All three are surfaces, so
  they belong to this plan's "Surfaces & shell" item; doing it in CSS avoids
  touching the ~40 views that call `ui.card()` directly.
- **Severity dots** in `dashboard_widgets/wizard_actions.py` were
  `bg-red-500` / `bg-amber-500` / `bg-sky-500`; sky blue has no place in the
  palette, so they became `.k-dot--danger/--warn/--info`.
- **Verified in a live browser**, not just in tests: Libre Franklin and both
  IBM Plex Mono weights report `loaded`, body ground computes to
  `rgb(243, 239, 231)` light / `rgb(23, 22, 19)` dark, the page title is
  weight 300 in ink, the drawer measures 236px and the header 60px.
- **Three amber spellings are left alone on purpose.** `forecast.py`'s
  Prophet-unavailable banner (`bg-amber-1 text-amber-10`) is the thing `3a`
  turns into a footnote; `setup.py`'s folder glyph is a decorative icon; and
  `dashboard.py` already spells its own light/dark pair. The fourth,
  `import_view/settings_section.py`'s currency warning, was a genuine miss and
  is now `k-trend--warn` like its siblings.
- **Left for the per-screen plans**, deliberately: `icon_badge_classes()`
  still builds Tailwind `bg-{color}-500/10` badges from each widget's
  registered colour (the `1c` dashboard plan merges those KPI cards), and
  `wizard.py`'s `_SECTION_COLORS` header bars stay until `3d`.

- **`INK` / `.k-ink` is separate from `.k-heading`** even though both resolve
  to `var(--k-ink)`. Figures and dense grid cells (`budget_plan` month cells,
  the credit-calculator payment, the net-worth total, keycaps) are ink text,
  not headings; giving them the heading class would have made a later change
  to heading colour silently repaint the budget grid.

- **The chart palette is wired, not just declared.** The mode-aware helpers
  (`chart_ink_color`, `chart_income_color`, `chart_expense_color`,
  `chart_accent_color`) replace the fixed light hexes in `cashflow_chart.py`,
  `savings_rate_trend.py`, `net_worth_trend.py`, `wizard_salary.py` and
  `money_flow.py` — a colour lookup, not a series rebuild, and it fixes a real
  legibility bug the tokens would otherwise have shipped: the cashflow net
  line was ink `#1C1A15` on a `#201F1A` dark card. `money_flow.py` also lost a
  hard-coded `#94a3b8`/`#334155` label pair in favour of `chart_text_color()`.
  `CHART_ACCENT_FILL` was a fixed light rgba used unconditionally (inherited
  from `CHART_TEAL_FILL`), so the two trend widgets drew a muted-brown area
  under an `#E8935B` line in dark mode; it is now `chart_accent_fill(is_dark)`
  like every other colour helper.

- **The 236px drawer needed the handoff's nav type and gutter, not just the
  width.** At Quasar's defaults (14px labels, a 56px avatar column) "Payment
  Calendar", "Monthly Readiness" and "Credit Calculator" wrapped to two lines
  inside a fixed `h-11` row and overflowed it — which is how
  `test_every_nav_entry_routes` failed once in a full e2e run while passing in
  isolation: a clipped label is an unreliable click target. `.k-nav-item` now
  uses the handoff's 13px label and a 19px icon with a 12px gutter, and
  `min-h-11` instead of `h-11` so a wrap could never clip again. Measured in
  the browser: all 25 entries are single-line 44px rows, the mini rail is
  64px, and expanding returns to 236px.

- **Six dark values are extrapolated, not quoted.** The handoff's dark table
  covers thirteen roles; `--k-surface-warm` (`#262420`), `--k-border-strong`
  (`#453F34`), `--k-disabled` (`#6E6656`), `--k-chip-dash` (`#453F34`),
  `--k-row-hover` (`#262420`) and `--k-neutral-bar` (`#8E8676`, unchanged) had
  no dark row, so they were derived by holding the light table's step between
  neighbouring surfaces. `--k-accent-text` and `--k-accent-light` both collapse
  to the dark accent `#E8935B`, which is what the handoff's own note
  ("Accent `#E8935B` (ink `#241C13` sits on it)") implies — dark mode has one
  accent, not three. `test_every_dark_token_is_also_declared_light` guards
  against a token existing in only one mode.
- **One deliberate value change in the sweep**: `payment_calendar.py`'s
  non-today day numbers moved from `text-slate-700` (ink-2) to `text-slate-500`
  (muted). Today's number had been the only `text-primary` figure on the page,
  and once accent left figures, ink-vs-ink-2 was too weak to read as "today".
  Muted for other days restores the contrast the accent used to carry; `3c`
  replaces this with the 2px ink border and `Today` label.

- **Two constants beyond the scope list**: `ACCENT_SURFACE` / `ON_ACCENT`
  (`.k-accent-surface`). The sweep requires `bg-teal-7` + `text-teal-1` to
  leave `wizard.py`'s Setup header, and teal no longer exists anywhere in the
  palette; a filled accent surface is the handoff's own token for that role.
  The subtitle there also gained `opacity-80`: `text-teal-1` was a *lighter
  tint* of the header colour, and `ON_ACCENT` alone is the full-strength
  on-accent ink, so without it the subtitle would have read as loud as the
  title.
- **Drawer width is set with `.props("width=236")`, not `ui.left_drawer(width=…)`.**
  This NiceGUI version's `LeftDrawer.__init__` takes no `width` argument
  (mypy catches it); the Quasar prop is the supported path. The mini rail is
  `mini-width=64`, with a key-only string for `props(remove=…)`.
- **`settings/appearance_tab.py` was not touched** — the scope's "(if it shows
  swatches)" condition does not hold: the tab is two toggles, no palette
  preview.
- **No `KAL-` scenario was added.** The handoff is explicit that "nothing in
  this redesign changes app behaviour"; this plan adds no user-facing
  capability, only presentation, so Working Agreement §5 does not bite. The
  contract is covered instead by `tests/unit/views/test_theme.py` (token
  values quoted from the handoff tables) and the extended
  `test_chart_utils.py`.
- **`chart_utils` constants were renamed, not aliased**: `CHART_TEAL` →
  `CHART_ACCENT`, `CHART_TEAL_FILL` → `CHART_ACCENT_FILL`, `CHART_NET_LINE` →
  `CHART_INK`. Five view modules import them; keeping teal-named aliases
  around would have re-introduced the vocabulary this plan removes. No series
  was rebuilt — only the colour each already asked for.

## Implementation

Landed on 2026-09-18.

| SHA | Author | Date | Message |
|---|---|---|---|
| `1860f2d` | Dawid (Ani) | 2026-09-12 | feat(theme): sand palette, Libre Franklin + IBM Plex Mono, design tokens |

**Files changed:**
- docs/architecture.md
- docs/plans/restyle-theme-tokens.md
- src/kaleta/pwa.py
- src/kaleta/static/fonts/ibm-plex-mono-400.woff2
- src/kaleta/static/fonts/ibm-plex-mono-500.woff2
- src/kaleta/static/fonts/libre-franklin-var.woff2
- src/kaleta/static/fonts/LICENSE.txt
- src/kaleta/static/manifest.json
- src/kaleta/views/budget_builder.py
- src/kaleta/views/budget_plan/grid.py
- src/kaleta/views/budget_plan/helpers.py
- src/kaleta/views/categories.py
- src/kaleta/views/chart_utils.py
- src/kaleta/views/credit_calculator.py
- src/kaleta/views/dashboard_widgets/cashflow_chart.py
- src/kaleta/views/dashboard_widgets/month_net.py
- src/kaleta/views/dashboard_widgets/net_worth_trend.py
- src/kaleta/views/dashboard_widgets/savings_rate_trend.py
- src/kaleta/views/import_view/settings_section.py
- src/kaleta/views/import_view/transfer_section.py
- src/kaleta/views/layout.py
- src/kaleta/views/net_worth.py
- src/kaleta/views/payees.py
- src/kaleta/views/payment_calendar.py
- src/kaleta/views/reports_canned/money_flow.py
- src/kaleta/views/reports/config_zone.py
- src/kaleta/views/safety_funds.py
- src/kaleta/views/theme.py
- src/kaleta/views/transactions/add_dialog.py
- src/kaleta/views/wizard_salary.py
- src/kaleta/views/wizard.py
- tests/unit/test_pwa.py
- tests/unit/views/test_chart_utils.py
- tests/unit/views/test_theme.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
