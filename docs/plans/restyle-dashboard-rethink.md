---
plan_id: restyle-dashboard-rethink
title: Restyle — desktop rethink: five top-nav sections, ⌘K palette, bands on desktop (artboard 1e)
area: dashboard
effort: large
status: draft
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle — desktop rethink (top nav, command palette, bands)

## Intent

`1f` gave the phone a dashboard that answers one question — *am I on
track this month?* — and the desktop kept the widget wall. Artboard `1e`
is the other half: the same safe-to-spend hero and the same three bands
at 1360px, and a 24-item drawer collapsed into five top-bar sections
(Overview / Money / Plan / Insight / Setup) with a ⌘K palette for
everything that does not fit in five. `NAV_GROUPS` in `layout.py`
already holds that grouping; this promotes it to the top bar.

Almost all of the machinery exists. `restyle-dashboard-mobile` shipped
`ReportService.safe_to_spend`, the `safe_to_spend` hero widget, `Band` /
`BAND_OF` / `bands_for_layout`, and the Watch band's four figures — all
of it written to be read at any width. What is left is a desktop layout
that uses them, a top bar, and a palette.

Depends on `restyle-dashboard` (`1c`) and `restyle-dashboard-mobile`
(`1f`). **The restyle index defers this one on purpose** — "revisit
after living with 4" — and `1c` is not merged yet. Arming this plan is a
decision to stop waiting.

## Scope

- **Top bar** (`layout.py`, ≥ `md`): the five `NAV_GROUPS` keys become
  five top-bar sections. A section opens a menu of its group's entries;
  the section carrying the current path is marked with the same
  `nav_active` rule the drawer and the tab bar already share. Pinned
  Dashboard and Wizard keep their places. The header stays 60px.
- **Drawer**: no longer the desktop navigation, but not deleted — it
  remains the phone's "More" surface (`1f`) and the `sidebar_mini`
  storage key keeps working. Above the breakpoint it is hidden.
- **Command palette** (`⌘K` / `Ctrl+K`, and the header's "Jump to…"
  field): a dialog listing every nav destination — the five groups'
  entries plus the pinned pair — filtered as you type, Enter navigates,
  Escape closes. Routes only; no actions, no search over data.
- **Bands on desktop** (`dashboard.py`): the same three bands as the
  phone, at desktop proportions — *Now* full width (hero left, needs-
  attention and two actions right), *Month* a 2-up grid, *Watch* four
  figures in one row as plain type on the ground, then "Latest" (recent
  transactions) below. `BAND_ORDER` and `bands_for_layout` are reused
  unchanged; only the container classes differ.
- **Drag-and-drop scoped to the Month band.** The SortableJS instance
  binds to the Month band's container instead of `#dash-grid`; the
  `/\_dashboard/layout` endpoint, `_validate_layout` and the legacy
  migration are untouched, and a widget outside Month is not draggable.
- **The hero joins the desktop default.** `safe_to_spend` goes into
  `DEFAULT_WIDGETS` at the head, which also makes `mobile_layout`'s
  prepend a no-op for new users.
- i18n: `nav.section_*`, `nav.palette_*`.
- BDD: `KAL-NAV-007` "five top-bar sections on a wide viewport"
  (@automated, e2e), `KAL-NAV-008` "⌘K reaches a page no section shows"
  (@automated, e2e), `KAL-DSH-008` "the desktop dashboard reads in three
  bands and only the Month band drags" (@automated, e2e).
- `docs/product/dashboard.md`: the Phone layout section becomes one
  section covering both widths.

Out of scope: any new widget; a palette that searches transactions,
payees or categories (routes only); touching `app.storage.user` keys;
`1b`; the mobile pass for screens other than `1f`/`3f`.

## Acceptance criteria

- `uv run pytest tests/unit/views/test_dashboard_bands.py -q`
- `uv run pytest tests/e2e/test_navigation.py tests/e2e/test_dashboard_mobile.py tests/e2e/test_dashboard_desktop.py -q`
- `uv run pytest tests/e2e/test_dashboard_customize.py -q`
- `grep -q "KAL-NAV-007" docs/bdd.md`
- `grep -q "KAL-NAV-008" docs/bdd.md`
- `grep -q "KAL-DSH-008" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` 1360px on seed data: matches artboard `1e` — five sections
  in the top bar, no drawer, hero carrying the page, Now / Month / Watch
  / Latest, and a card dragged inside Month stays inside it. 390px is
  unchanged from `1f`, tab bar included.

## Touchpoints

- `src/kaleta/views/layout.py` (top bar, palette, drawer breakpoint),
  `theme.py` (`.k-topnav*`, `.k-palette*`)
- `src/kaleta/views/dashboard.py` (desktop bands, Sortable target),
  `dashboard_widgets/registry.py` (`DEFAULT_WIDGETS`)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/product/dashboard.md`, `docs/bdd.md`
- `tests/e2e/`, `tests/unit/views/`

## Open questions

1. **Which four figures does the Watch band carry?** `1f` shipped net
   worth, the 30-day balance, the year's savings rate and the
   year-to-date net, because that is what the `1f` plan's Scope named.
   The `1e` artboard shows net worth (+1,90% vs June), *savings rate,
   6-mo avg*, balance in 30 days (labelled with the model), and *safety
   fund cover* (4,6 mo against a 6-month target). Default: **take the
   artboard's four**, since `1e` is the artboard being implemented, and
   change `1f` to match in the same commit so the two widths do not
   disagree. Safety-fund cover comes from `reserve_fund_service`.
2. **Does the `1f` tab bar become Overview / Money / + / Plan /
   Insight?** That is what the canvas shows, and it only became
   possible once the five sections exist; `1f` shipped Home / Ledger /
   + / Plan / More because "More" was the only way to reach the long
   tail. Default: **yes** — the five sections, with the palette
   reachable from the header on both widths. This is a change to a
   shipped screen and belongs in this plan, not a follow-up.
3. **Does the drawer survive at all on desktop?** Default: **no** — the
   top bar replaces it, and `sidebar_mini` becomes dead storage that is
   read but never written. Deleting the key is a migration this plan
   does not want.
4. **Does ⌘K collide with anything?** Default: browsers reserve ⌘K in
   the address bar only when the address bar has focus, so a
   page-level handler is safe; bind both `⌘K` and `Ctrl+K`, and leave
   the existing `?` and `Alt+N` handlers alone.

## Implementation notes

_Filled in as work progresses._
