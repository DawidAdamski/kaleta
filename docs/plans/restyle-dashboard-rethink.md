---
plan_id: restyle-dashboard-rethink
title: Restyle — desktop rethink: five top-nav sections, ⌘K palette, bands on desktop (artboard 1e)
area: dashboard
effort: large
status: in-progress
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
  remains the phone's "More" surface (`1f`). Above the breakpoint it is
  hidden. ~~and the `sidebar_mini` storage key keeps working~~ — see
  Implementation notes §3: with no docked drawer there is nothing left to
  collapse, so the mini toggle and its Settings → Appearance card went
  with it. The *key* is untouched, as "Out of scope" requires: it is left
  unread in whatever storage already holds it, not migrated or deleted.
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
  `/\_dashboard/layout` endpoint and the legacy migration are untouched,
  and a widget outside Month is not draggable. ~~`_validate_layout` is
  untouched~~ — it had to change, and the reason is under *Found by the
  second review*: with every banded widget now posted, a size it did not
  recognise deleted the widget instead of correcting it.
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
- `[owner]` Open question 2 was decided **against** this plan's stated
  default: the `1f` tab bar keeps Home / Ledger / + / Plan / More rather
  than becoming the five sections. The reasoning is in Implementation
  notes §2; it is a one-file change to `TAB_BAR_ENTRIES` if the owner
  wants the default after all.
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

### Open questions, as resolved

1. **Watch figures** — took the artboard's four: net worth, savings rate
   (6-month average), balance in 30 days, safety-fund cover. `1f` moved
   with them in the same branch, so the two widths cannot disagree, and
   `KAL-DSH-007` was re-pointed to match. Cover is the first
   `EMERGENCY` fund's `months_of_coverage` from
   `ReserveFundService.list_with_progress()`; `None` — no fund, an empty
   one, or no spending in 90 days to measure against — reads "—" rather
   than a zero, because no fund and zero months of cover are not the
   same news.
2. **The `1f` tab bar** — **not** changed to Overview / Money / + /
   Plan / Insight, against this plan's stated default. The Scope section
   — the binding contract — does not list the tab bar, and the change
   would rewrite a shipped, covered screen (`KAL-NAV-006`). It would
   also cost the phone its "More": the five sections are *menus*, and a
   phone tab that opens a menu of eight setup pages is worse than a tab
   that opens the drawer holding them. The palette is on the phone
   header (`.k-phone-search`), so the long tail has a second way in
   either way. **Left for the owner to call** — it is a one-file change
   to `TAB_BAR_ENTRIES` if they want it.
3. **Drawer on desktop** — gone as *navigation*, kept as the phone's
   "More" surface. It is now an overlay at **every** width
   (`breakpoint=99999`), not merely hidden: a drawer Quasar considers
   "desktop" reserves 236px of page gutter whether or not you can see
   it, and `1f`'s `breakpoint=767` would have stood it open beside the
   top bar between 768px and 1023px. `sidebar_mini` did **not** survive:
   with no docked drawer there is nothing to shrink, so the mini toggle,
   `_MINI_PROPS`, `is_mini`, `toggle_mini`, the Settings → Appearance
   sidebar card and the four now-orphaned i18n keys all went. No
   storage migration — an unread key costs nothing.
4. **⌘K** — bound alongside `Ctrl+K` in the existing `_global_key`
   handler; `?` and `Alt+N` untouched. No collision observed: the
   browser claims ⌘K only while the address bar has focus.

### Decisions worth a reviewer's time

- **Section labels are new keys, not the group headings.** `NAV_SECTIONS`
  reuses the five `NAV_GROUPS` keys for grouping but labels them from
  `nav.section_*`: "Monthly cycle" and "Plans & funds" are names for a
  sidebar heading, not for a 60px bar that must hold five of them, a
  search and the account controls. The canvas's own regrouping
  (Overview / Money / Plan / Insight / Setup) was *not* adopted — it
  would have moved pages between groups, which is a navigation-taxonomy
  change this plan does not scope.
- **`Band.LATEST` is new.** `1f` banded recent transactions into
  *Month*, where at desktop width a ten-row log sat among the metric
  cards. A log is not a metric; it now has its own band under
  everything that is. The phone picked the band up for free.
- **`mobile_layout` / `with_hero` is gone entirely.** `1f` prepended the
  hero to whatever the stored layout held, because the hero was not a
  default widget then. It is one now — so the prepend made the Customize
  checkbox a lie at both widths (unticking `safe_to_spend` did nothing),
  and, worse, the layout POST serialises `#dash-bands [data-widget-id]`,
  so the first drag inside Month wrote the hero back into storage and
  silently re-ticked it. The hero is an ordinary default widget now:
  every new profile and every *Reset widgets* leads with it, and a
  profile stored before it existed gets it by ticking it once.
  `KAL-DSH-007`'s "although Customize does not have it ticked" line went
  with the prepend.
- **Scoping the drag to Month took no JS changes.** `#dash-grid` *is*
  the drag scope: SortableJS, the resize button and the layout endpoint
  all key off that id, so moving the id to wrap the Month band alone
  moved all three. The one change needed was the *POST* query —
  `__kaletaPostDashLayout` now serialises `#dash-bands [data-widget-id]`
  rather than `#dash-grid …`, or a drag inside Month would have saved a
  layout that had dropped the hero and the Latest list.

### NiceGUI / Quasar findings

- Quasar's colour helpers (`.text-primary`) are `!important`, and
  `ui.button` defaults to `color='primary'` — so a top-bar button keeps
  the brand apricot no matter what the stylesheet says. Every bar button
  passes `color=None`.
- `icon-right` is an icon **name**, not a flag: `icon=expand_more` plus
  a bare `icon-right` put every chevron in front of its label.
- Two-class selectors (`.q-btn.k-topnav-item`) beat Quasar's own
  single-class rules without `!important`.
- `hidden md:flex` loses to Quasar's stylesheet order; `.k-topnav`
  carries its own `@media` rule at 768px, like `.k-tabbar` before it.
- The palette's field takes focus when the dialog's transition *ends*,
  not when it mounts — type before that and the keystrokes land on
  `<body>`. The e2e tests wait for the caret; a person typing inside
  ~300ms of ⌘K would lose the first characters, which is a real if minor
  nit left for the chore inbox.

### Found by review, after the first pass

- The palette's "Jump to…" pill is a *sibling* of `.k-topnav`, not a child
  of it, so hiding the row left a 390px header carrying both the pill and
  the `.k-phone-search` icon — two controls for one dialog. The pill
  carries the breakpoint itself now, and a phone test asserts there is
  exactly one way in at each width.
- Every band but Watch was skipped when empty, and Customize will happily
  leave Month empty (it insists on one widget overall, not one per band).
  That took the grid, the "Edit this band" button and the empty-state
  placeholder off the page together. Month is now rendered empty too — it
  is the drag scope and the empty state, not just a group of cards.
- The Watch band formatted its savings rate unconditionally, and
  `average_savings_rate_pct` answers `Decimal("0")` for no months at all:
  a new ledger read "0.0%", a figure it does not have, two rows above a
  "—" put there to avoid exactly that. `_watch_rate_label` is the pure
  function that decides, with unit tests.
- Enter on a freshly opened palette navigated, because an empty needle is
  in every label. It is a no-op until something is typed.
- `docs/adr/009` still listed `sidebar_mini` as a live key.

### Found by the second review

- **The first resize or drag in Month deleted the other bands.** The layout
  POST serialises every banded widget, but a widget outside the grid
  carried no `data-cols`, so it posted as 1×1 — a size none of the hero,
  the banner or the Latest list allows — and the endpoint *dropped* those
  rows. The wrapper carries its size now, and `_validate_layout` falls back
  to `default_size` instead of dropping a widget, which is what
  `resolve_user_layout` already does on the way in: the size is the
  layout's business, the widget is the user's. Two of its unit tests
  changed with the contract. An e2e now fires a real resize, re-reads
  storage and checks the other bands are still there.
- `page_layout(title)` had no reader left after the header lost its page
  title, while its docstring claimed the argument still named the page —
  so it names the browser tab now (`ui.page_title`), which is the one
  place a page's name was never shown.
- `dashboard_widgets.edit_layout` was orphaned by the Month band's own
  button; deleted from both locales.

### Found by the third review

- **The bar wrapped at 768px**, the very width it takes over at: five
  sections, two pinned entries, a pill and three icon buttons do not fit
  one 60px line, and "Setup" ended up on a second one the header has no
  room for. Below 1024px the two pinned entries and the pill keep their
  icons and drop their words. The words are dropped with `font-size:0`,
  not `display:none`: the label is a Quasar-rendered `span.block` that a
  display rule in this stylesheet does not win against, and zero type
  collapses it just as well while leaving the name in the document for a
  screen reader. An e2e asserts one line at 768px.
- **The section menus rendered without their icons.** `q-item` has no
  `icon` prop, so `ui.menu_item(...).props("icon=…")` set an attribute
  Quasar ignores — while the palette beside it, which builds rows out of
  `ui.icon`, showed the same icons correctly. The entries build their own
  row now.
- `_safety_fund_cover` took the first emergency fund the service happened
  to return. Every fund's cover divides by the same trailing monthly
  spend, so two emergency funds cover the *sum* of their months; the rule
  is a pure `_emergency_cover` with unit tests.
- `nav_destinations` calls itself the only complete list of routes and
  nothing asserted it: a group added to `NAV_GROUPS` without a
  `NAV_SECTIONS` row would vanish from the bar *and* the palette, which
  since `1e` means off the desktop entirely. `test_nav_destinations.py`
  pins it.
- Stale copy: the Customize dialog still said "Use Edit layout", and
  `KAL-NAV-005` still described a sidebar at any width.

### Housekeeping

- The Settings → Appearance sidebar card that went with the mini toggle
  was never in `docs/bdd.md` — there is no `KAL-` scenario describing a
  sidebar default state, so there was nothing to retag. Recorded here
  rather than left as a silent removal.
- **Chore-inbox sized, not filed:** palette rows are clickable `div`s
  with no `role="option"` and no focus, so a keyboard reaches only the
  first match (via Enter); and the palette's field takes focus when the
  dialog's transition ends, so a very fast typist loses the first
  characters after ⌘K.

### Verification

Layout claims were checked in a real browser at 1360px rather than
reasoned about, with a throwaway probe under `tests/e2e/` (deleted).
That is what caught the apricot bar, the reversed chevrons, and the
drawer gutter.
