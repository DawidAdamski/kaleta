---
plan_id: restyle-fidelity-shell-dashboard
title: Restyle fidelity — the drawer shell back on desktop, dashboard to artboards 1c / 1d / 1f
area: dashboard
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#dashboard
---

# Restyle fidelity — shell and dashboard

## Intent

The restyle programme shipped fifteen plans and the app still does not look
like the mockup. Three reasons, all found by reading the archive:

1. Thirteen of the fifteen plans never open `Kaleta Dashboard.dc.html`. They
   were written from the handoff README's prose, and composition — what is a
   card and what is bare type, what sits on the title row, how wide the bar
   is — lives in the markup, not in the prose.
2. Every plan closed its comparison with the artboard as `[manual]`, "the
   owner's visual pass". No step ever rendered the app next to the artboard.
3. `restyle-dashboard-rethink` built artboard `1e`, which **is not a target**.
   The owner's targets are `1c` (light), `1d` (dark) and `1f` (phone) for the
   dashboard, and `2a`–`2d`, `3a`–`3f` for the working screens. Every one of
   those desktop artboards has a paper header and a docked drawer — 236px on
   the dashboard, 64px mini on the working screens. `1e` replaced that drawer
   with a top bar on *every* page, so today no screen can match its artboard.

This plan undoes (3) on desktop and brings the dashboard to `1c` / `1d` /
`1f`, under the fidelity loop that fixes (1) and (2). The working screens
follow in `restyle-fidelity-screens`, which depends on this shell.

## Method (binding — this is what the first pass lacked)

For each artboard in scope:

1. Read `docs/design/restyle/artboards/<id>.html` **whole**. It is 10–25 KB.
   That markup is the spec: element order, nesting, and every inline value.
   The README is commentary on it, not a substitute for it.
2. `uv run python scripts/restyle_fidelity.py shoot <id>` — an ephemeral
   seeded app and the artboard, same width, same theme, in `.fidelity/<id>/`.
3. **Look at both pictures** (`artboard.png`, `app-<width>.png`).
4. Write `docs/design/restyle/fidelity/<id>.md`: one row per element
   compared, with the values observed on each side. Replace the template's
   generic rows with the artboard's real elements.
5. Fix every `open` row by transcribing the artboard's structure and values
   into NiceGUI + `theme.py` tokens. A value that recurs becomes a token; a
   one-off stays a Tailwind arbitrary value (`text-[32px]`). Do not port the
   HTML, and do not "interpret" it either — same elements, same order, same
   numbers.
6. Shoot again. Repeat until `check <id>` passes.

`deviation` is for what cannot or should not match: sample data vs seed data,
an SVG sketch vs a real ECharts series, a Quasar control with no equivalent,
an owner decision recorded in this plan. It is not for "close enough".

## Scope

- **Shell, ≥ `md`** (`layout.py`, `theme.py`): the docked drawer returns as the
  desktop navigation — 236px expanded, 64px mini, the mini toggle back in the
  header, `sidebar_mini` read again, and the Settings → Appearance card that
  went with it restored. The toggle carries `data-drawer-mini-toggle` (the
  shoot script uses it to put each artboard in the state it is drawn in).
  The five top-bar sections (`_top_nav`, `.k-topnav*`) go.
  Header per `1c` / `2a`: 60px, paper, wordmark · divider · current page name,
  search pill, dark toggle, avatar. Drawer per `1c`: ground colour, quiet
  index, uppercase group eyebrows, active item on paper with accent icon.
  `7256217` is the last commit with the docked drawer — read
  `git show 7256217:src/kaleta/views/layout.py` for how it was wired, but do
  not revert wholesale: fixes that landed since (browser-tab titles, the
  768px header rules that still apply, `nav_active`) stay.
- **Shell, < `md`**: unchanged. The `1f` tab bar, the drawer behind "More".
- **Dashboard, ≥ `md`** (`dashboard.py`, `dashboard_widgets/`): one widget
  grid again, as `restyle-dashboard` built it — Balance and This-month cards,
  the full-width accent "needs attention" banner, drag-and-drop over the whole
  grid. Bands become phone-only. `safe_to_spend` leaves the head of the
  desktop `DEFAULT_WIDGETS`; it stays the phone hero through `mobile_layout`.
  Then the fidelity loop on `1c` and `1d`.
- **Dashboard, < `md`**: the fidelity loop on `1f`.
- **BDD and tests**: `KAL-NAV-007` (five top-bar sections) and `KAL-DSH-008`
  (desktop bands, Month-only drag) describe behaviour this plan removes.
  Rewrite them to the behaviour that replaces it — a docked drawer whose mini
  state persists; a desktop grid that drags as a whole — and update
  `tests/e2e/test_navigation.py` and `tests/e2e/test_dashboard_desktop.py` to
  match. This is a behaviour change by plan, not green-washing; say so in the
  PR description. `KAL-NAV-008` (⌘K) stays as is.
- `docs/product/dashboard.md`: desktop section back to the grid; bands
  described as the phone layout.

Out of scope: the working screens (next plan); any service change —
`ReportService.safe_to_spend`, `Band` / `BAND_OF` / `bands_for_layout` and the
Watch figures all stay for the phone; new widgets; artboards `1a`, `1b`, `1e`.

### Scope amendment — the two widgets `1f` redraws (agreed during implementation)

`1f` draws **Needs attention** and **Latest** differently from `1c`: a paper
card of 44px rows with chevrons, and 52px two-line rows instead of a
five-column table. Neither is a restyle of the widget the app has — a
widget's render signature is `(session, is_dark)` and is never told the
width, so either means changing the signature every widget in the catalogue
is registered with.

That is a registry change and new behaviour needing its own `KAL-` scenario,
so it is **deferred to [`restyle-fidelity-phone-widgets`]
(restyle-fidelity-phone-widgets.md)**, which exists as a draft and names
both. Rows 10 and 13 of `1f.md` are `deviation` against that plan, not
against a preference. The `[owner]` criterion below is where the deferral
gets accepted or sent back.

## Acceptance criteria

- `uv run python scripts/restyle_fidelity.py check 1c`
- `uv run python scripts/restyle_fidelity.py check 1d`
- `uv run python scripts/restyle_fidelity.py check 1f`
- `uv run pytest tests/e2e/test_navigation.py tests/e2e/test_dashboard_desktop.py tests/e2e/test_dashboard_mobile.py tests/e2e/test_dashboard_customize.py -q`
- `grep -q "KAL-NAV-007" docs/bdd.md`
- `grep -q "KAL-DSH-008" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[owner]` Opens `.fidelity/1c/index.html`, `.fidelity/1d/index.html` and
  `.fidelity/1f/index.html` and agrees with the three reports — in particular
  with every row marked `deviation`.

## Touchpoints

- `src/kaleta/views/layout.py`, `src/kaleta/views/theme.py`
- `src/kaleta/views/settings/appearance_tab.py`
- `src/kaleta/views/dashboard.py`, `src/kaleta/views/dashboard_widgets/`
  (`registry.py` for `DEFAULT_WIDGETS`, `helpers.py`, the two KPI cards,
  `wizard_actions.py` for the banner)
- `src/kaleta/i18n/locales/en.json`, `pl.json` (drop `nav.section_*` if
  nothing reads them)
- `docs/design/restyle/fidelity/1c.md`, `1d.md`, `1f.md`
- `docs/bdd.md`, `docs/product/dashboard.md`, `tests/e2e/`

## Open questions

1. **The header's search pill.** `1c` / `2a` label it "Search transactions,
   payees…"; what exists is the ⌘K palette, which finds routes only. Default:
   **keep the palette behind the pill and ⌘K, keep its honest "Jump to…"
   label**, and record the label as a `deviation`. A data search is its own
   plan.
2. **Stored layouts that gained `safe_to_spend`** while `1e` was live.
   Default: **leave them** — it is a registered widget the user can untick in
   Customize; silently deleting a card from a saved layout is worse than
   leaving one.
3. **Default drawer state.** The artboards draw it expanded on the dashboard
   and mini on working screens, but it is one user preference, not a
   per-page one. Default: **expanded for a new user, then whatever
   `sidebar_mini` says**; the shoot script sets the state per artboard.

## Implementation notes

### Open questions, resolved

1. **The header's search pill** — default taken. The pill and ⌘K open the
   same route palette and keep the honest `nav.palette_open` label
   ("Jump to…"). Recorded as `deviation` row 3 of `1c.md`.
2. **Stored layouts that gained `safe_to_spend`** — default taken. Nothing
   deletes it from a saved layout; it is simply out of `DEFAULT_WIDGETS`, so
   a new profile and *Reset widgets* do not add it, and anyone who has it can
   untick it in Customize. `mobile_layout` prepends it on a phone only when
   the stored layout does not already carry it, so it never appears twice.
3. **Default drawer state** — default taken. Expanded for a new user, then
   whatever `sidebar_mini` says; Settings → Appearance sets it, and the
   header's chevron (`data-drawer-mini-toggle`) flips it. The shoot script
   puts the drawer in each artboard's state through that attribute.

### Decisions made while transcribing

- **Icon face.** Every artboard draws Material Symbols Outlined; Quasar's
  default is the *filled* `material-icons`, and a filled 19px glyph beside
  13px type is a blob. NiceGUI already self-hosts all four Google Material
  Icons styles, so one rule — `.q-icon.material-icons{font-family:'Material
  Icons Outlined'}` — moves the whole app onto the outlined face without a
  second font to fetch and without an `o_` prefix on several hundred
  `ui.icon` calls (which would leave whichever were missed filled). It is a
  `theme.py` change made for `1c`/`1d`/`1f`; it also moves the working
  screens towards their own artboards, which `restyle-fidelity-screens`
  will confirm.
- **Two paddings.** NiceGUI pads `.nicegui-content` with 1rem and
  `.k-dash-page` adds the artboard's 36/40/44 on top, which put the grid at
  276+16px and narrowed the columns from 246 to 238. `.nicegui-content:has(>
  .k-dash-page){padding:0;gap:0}` scopes the fix to the dashboard.
- **`.k-drawer` is the content, not the aside.** NiceGUI puts a drawer's
  classes on Quasar's `.q-drawer__content`, so the ground, the hairline and
  the 22/24 padding live there — and have to out-specify
  `.nicegui-drawer{padding:1rem}`, which is why the rule is
  `.q-drawer__content.k-drawer`.
- **The banner's pill needed `color=None`.** Quasar's colour helpers are
  `!important`, so NiceGUI's default `primary` drew the accent on the
  accent — a label, not a button. Same trick the drawer-mini toggle and the
  title-row pills use.
- **The account/header controls.** Artboards `1c` and `2a` end the header
  with a 28px initials disc and nothing else, so "log out" and "close
  database", which had buttons of their own, moved into the menu that disc
  already dropped.
- **Header on a phone.** The divider and the page name are `display:none`
  below 768px. Kept, they pushed the avatar onto a second line that a header
  fixed at 60px clips — visible in the first `1f` shot as the avatar sitting
  over the page eyebrow.
- **Sentence case.** `1c` sets card titles in sentence case, so
  `dashboard_widgets.budget_variance_month`, `top_merchants` and
  `recent_transactions`, plus `dashboard.cashflow_chart`/`view_all`, lost
  their title case. `dashboard.month_in` / `month_out` are new: the artboard
  labels the three month figures "In" and "Out", because three 26px figures
  share a half-width card.
- **`.k-table` header tracking stays at .14em.** `1c`'s transactions grid
  says `.16em`, but that grid is the dashboard's copy of the ledger, and the
  ledger's own header in `2a` says `.14em`. One table style, the ledger's.
- **`--k-rule`, new.** `#DCD4C2` — the band rule on the phone, the mini
  drawer's separators — appears on eleven artboards, which makes it a token
  rather than an arbitrary value. It sits between `--k-hairline` (a card's
  internal rule) and `--k-border` (what a control is drawn with); in dark it
  is `#3D392F`, the value `1d` uses for the same job.
- **Two heroes, one helper.** `hero_figure` now takes `weight` and
  `tracking` beside `size`, because the artboards set two: `1c`'s balance
  figure at 54px/500/-.035em and `1f`'s safe-to-spend at 46px/400/-.04em.
- **`.k-split`'s track is `--k-border`.** Both artboards that draw one —
  `1f`'s safe-to-spend and `3b`'s balance sheet — fill it with `#E2DBCC`;
  the class had `--k-surface-sunken`. The height is a modifier
  (`.k-split--hero`, 9px on a 5px radius) because `3b` draws the same bar at
  12px on 6px.
- **`chart_utils.py`, outside the Touchpoints list.** `1c` draws the
  cashflow net line in `--k-accent-light` (`#DE7B45`), a shade up from the
  accent a surface is filled with, and its symbols paper-filled — so
  `CHART_ACCENT_SERIES`, `CHART_SURFACE` and two helpers were added there.
  Dark has one apricot, so `chart_series_accent_color` and
  `chart_accent_color` agree in `1d`. Nothing that already read
  `chart_accent_color` changed.
- **`KAL-NAV-009`, new.** The avatar's menu holds log out and "close
  database", which had buttons of their own; a menu is where that behaviour
  now lives, so it gets a scenario and an e2e test rather than being a
  silent move.

### Left for the owner, or for the next plan

- **`1f`'s phone-only renderings.** Deferred by the scope amendment above
  to [`restyle-fidelity-phone-widgets`](restyle-fidelity-phone-widgets.md),
  drafted in this PR: "Needs attention" as a paper card of 44px rows with
  chevrons, and "Latest" as two-line rows instead of a five-column table.
  Recorded as `deviation` rows 10 and 13 of `1f.md`, each pointing at that
  plan.
- **The phone tab bar.** Scope excludes it in as many words ("Shell,
  < `md`: unchanged"). `1f` draws it 72px tall with a 52px ink centre disc;
  what shipped is 61px with a 44px accent disc, and the labels differ
  (Home/Ledger/Plan/More against Overview/Money/Plan/Insight). Recorded as
  `deviation` rows 15 and 16 of `1f.md` for whichever plan next opens the
  phone shell.
- **`scripts/restyle_fidelity.py` uses port 8082**, which is also
  `tests/e2e/test_demo_banner.py`'s `DEMO_PORT`. A `shoot --base-url` app
  left running fails that one e2e test with a login timeout that says
  nothing about the collision. One line for the Chore inbox.

### Behaviour this plan removes, by plan

`KAL-NAV-007` and `KAL-DSH-008` were rewritten, and
`tests/e2e/test_dashboard_desktop.py` with them: the five top-bar sections
and the Month-band-only drag are gone, replaced by a docked drawer whose
mini state persists and a grid that drags as a whole. `KAL-NAV-008` (⌘K) is
unchanged. `nav.section_*` and `dashboard.band_edit_month` were dropped from
both locales; `common.toggle_sidebar`, `settings.sidebar*` and
`dashboard_widgets.edit_layout` came back.

