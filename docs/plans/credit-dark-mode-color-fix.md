---
plan_id: credit-dark-mode-color-fix
title: Credit — fix unreadable colours in dark mode
area: credit
effort: small
roadmap_ref: ../roadmap.md#credit
status: draft
---

# Credit — fix unreadable colours in dark mode

## Intent

The Credit page (`src/kaleta/views/credit.py`) and its row helper
`_render_card` use hardcoded Tailwind / Quasar colour names —
`text-slate-500`, `amber-7`, `negative`, `positive` — that were
chosen for the light palette. In dark mode several of these
collapse against the slate-800 surface (`text-slate-500`
sits on rgb(30,41,59) — contrast ratio under 3:1) and the
utilization linear-progress bar with `color="amber-7"` is rendered
with a light-mode amber that disappears on the dark card.

This plan audits every colour-bearing class on the Credit page
and migrates them to the project's existing dark-aware tokens
(`AMOUNT_*`, `BODY_MUTED`, `SECTION_CARD`, etc.) plus targeted
DARK_CSS overrides for the cases where a literal class is the
only sensible choice.

## Scope

- **Audit pass** — list every occurrence of the offending
  classes in `views/credit.py` (≈ 6 of `text-slate-500`, 2 of
  `amber-7`, plus `positive` / `negative` chips and progress).
  Same audit on `views/credit_calculator.py`.
- **Replace `text-slate-500` muted captions** with `BODY_MUTED`
  (already dark-aware via `.k-muted`).
- **Utilization colour helper** — keep the three-way `green /
  amber / red` semantics, but return *theme-aware* tokens:
  - low → `text-green-7` (already overridden in DARK_CSS).
  - mid → `text-amber-7` (already overridden in DARK_CSS to
    `rgb(252,211,77)`).
  - high → `text-red-7` (already overridden).
  - For the `ui.linear_progress(color=...)` call, Quasar
    colour names map to `bg-<name>` internally; the existing
    DARK_CSS handles `bg-amber-1` / `bg-red-1` tints but not
    the **solid** progress fill. Add three new rules:
    - `.body--dark .q-linear-progress--positive .q-linear-progress__model`
    - `.body--dark .q-linear-progress--amber-7 .q-linear-progress__model`
    - `.body--dark .q-linear-progress--negative .q-linear-progress__model`
    Each sets `background:rgb(...)` to the same brightened
    palette used for the text classes, so the bar reads
    correctly on slate-800.
- **Status chip** — `ui.chip(color=...)` paints the chip
  background literally. Verify in dark mode that
  `positive` / `amber-7` / `negative` chip backgrounds clear
  AA contrast against the surface; if not, override
  `.body--dark .q-chip--positive`, etc., in DARK_CSS using
  the same brightened colours.
- **Loan amortization table** (lines ~415–490 in `credit.py`) —
  `text-slate-500` headers and rows replaced with `BODY_MUTED`
  / `text-grey-7` (also dark-aware).
- **No structural change** to the Python view code beyond
  swapping class strings; this stays a pure styling fix.

Out of scope:
- Light-mode visual changes — colours should remain identical
  in light mode; the diff should be visible only in dark mode.
- Refactoring `_utilization_color` into a shared theme helper
  (could happen later when other pages adopt the same pattern).
- Reworking the credit calculator's chart series colours.

## Acceptance criteria

- Toggle dark mode on `/credit`. Every label, caption, chip,
  and progress bar passes the WCAG AA contrast ratio (4.5:1
  for text, 3:1 for non-text indicators) against its surface.
- Utilization progress bar at 25% / 50% / 80% renders
  green / amber / red, all clearly visible on the dark slate
  card.
- Loan amortization table headers and "—" placeholder rows
  are legible.
- Light mode is visually unchanged (regression check on a
  before/after screenshot).

## Touchpoints

- `src/kaleta/views/credit.py` — class swaps in `_render_card`
  and loan render helpers.
- `src/kaleta/views/theme.py` — append the three
  `q-linear-progress` dark overrides to `DARK_CSS`; possibly
  three `q-chip--*` overrides if the audit shows they are needed.
- `src/kaleta/views/credit_calculator.py` — same pattern for any
  hardcoded `text-slate-*` it carries.
- No model / migration / i18n change.

## Open questions

1. **Override the chip background or its outlined border?**
   The chips currently use `.props("dense outline")` so only
   the border is coloured. The brightened text overrides may
   already make outlined chips readable; only override the
   background if the audit fails.
2. **Why are the bars literally invisible?** Confirm during
   implementation: it may be that Quasar's `.body--dark .bg-amber-7`
   already uses a dim variant. The fix is to add explicit
   overrides matching the brightened text colours.
3. **Should `_utilization_color` move to `theme.py`?** Default:
   no, single-use; revisit if a second page needs it.

## Implementation notes
_Filled in as work progresses._
