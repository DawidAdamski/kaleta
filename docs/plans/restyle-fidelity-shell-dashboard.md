---
plan_id: restyle-fidelity-shell-dashboard
title: Restyle fidelity — the drawer shell back on desktop, dashboard to artboards 1c / 1d / 1f
area: dashboard
effort: large
status: draft
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

_(filled in as work progresses)_
