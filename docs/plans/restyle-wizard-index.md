---
plan_id: restyle-wizard-index
title: Restyle — Financial Wizard as mentor card + setup done-cards + a plain two-column routines index (artboard 3d)
area: wizard
effort: small
status: draft
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Restyle — Financial Wizard: mentor card, setup done-cards, routines index

## Intent

`views/wizard.py` paints six section cards with saturated header bars in
six hues (`_SECTION_COLORS`) and thirteen steps, of which eight are
"Coming soon". Artboard `3d` reorders the page: hero → **mentor
suggestion** as a single accent-bordered card → **Setup** as four
compact done-cards (collapsed once `all_done`, as now) → **Routines**
as one plain two-column index ranked by readiness, not by section: the
steps with routes render in ink with an `Open` action, the ones without
render muted with a single quiet label. `_SECTION_COLORS` goes away.

Depends on `restyle-theme-tokens`.

## Scope

- **Drop `_SECTION_COLORS`** and the per-section header bars; sections
  become eyebrow labels inside the index (kept for i18n / grouping, no
  colour).
- **Hero**: page title + one-line subtitle (existing keys); remove the
  global "Coming soon" badge next to the title (the
  `wizard-unplanned-radar` draft also claims this rider — whichever
  ships first does it; the other drops the item).
- **Mentor card**: single card with a 3px `--k-accent` left border,
  `lightbulb` icon, the top suggestion, dismiss action; "all quiet"
  state as a one-liner. `wizard_mentor_dismissed` storage unchanged.
- **Setup**: four compact done-cards (icon, title, ✓ / `Open`), 4-up
  grid, collapsed behind the existing expansion when `all_done`
  (`wizard_onboarding_open` unchanged).
- **Routines index**: two columns (stack under `md`), one row per step:
  icon, title, 11.5px description, right-side `Open →` (accent text)
  for steps in `_STEP_ROUTES`; steps without a route: muted text and a
  10.5px uppercase label. Rows sorted: routed first (keep section
  order within), then unrouted. Label wording: **"Not built"** per the
  handoff — see open question.
- i18n: `wizard.not_built` (replaces `wizard.coming_soon` usages on
  this page only; keep the key for other pages).
- No BDD change (presentational); e2e navigation coverage in
  `test_wizard_actions_widget.py` / `test_navigation.py` must still
  pass.

Out of scope: any wizard step page, mentor rules, new steps (the draft
`wizard-*` plans), the dashboard wizard banner (`restyle-dashboard`).

## Acceptance criteria

- `uv run pytest tests/e2e/test_wizard_actions_widget.py tests/e2e/test_navigation.py -q`
- `test "$(grep -c '_SECTION_COLORS' src/kaleta/views/wizard.py)" = 0`
- `grep -q "not_built" src/kaleta/i18n/locales/pl.json`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data with setup complete: mentor card first with an
  accent border, four collapsed done-cards, then a two-column index with
  five `Open →` rows in ink and eight muted rows; no coloured header
  bars anywhere. Compare to artboard `3d` in light and dark.

## Touchpoints

- `src/kaleta/views/wizard.py`
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/product/financial-wizard.md` (page structure paragraph)
- `docs/plans/wizard-unplanned-radar.md` (drop the badge rider if this
  ships first — a one-line edit to a draft plan is allowed)

## Open questions

1. "Not built" vs "Coming soon" in a public repo? Default: **"Planned"**
   (`wizard.not_built` key, PL "W planach") — neutral, honest, less
   blunt than the prototype; the owner can change the string.

## Implementation notes

_Filled in as work progresses._
