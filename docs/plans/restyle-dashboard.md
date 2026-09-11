---
plan_id: restyle-dashboard
title: Restyle — Dashboard in the sand palette, merged KPI cards, quiet drawer (artboards 1c/1d)
area: dashboard
effort: medium
status: draft
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

_Filled in as work progresses._
