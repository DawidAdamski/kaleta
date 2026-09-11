---
plan_id: restyle-theme-tokens
title: Restyle — sand palette, fonts and mono amounts in theme.py (handoff step 1)
area: theme
effort: medium
status: draft
roadmap_ref: ../roadmap.md#ux
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
- `test -f src/kaleta/static/fonts/ibm-plex-mono-var.woff2`
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
- `[manual]` Contrast: body and label text on `#F3EFE7` clears 4.5:1
  (spot-check muted `#6B6353` and eyebrow `#6E6656`).

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

_Filled in as work progresses._
