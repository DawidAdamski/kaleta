---
plan_id: settings-panel-color-fix
title: Settings — fix panel colours in light and dark mode
area: settings
effort: small
roadmap_ref: ../roadmap.md#settings
status: draft
---

# Settings — fix panel colours in light and dark mode

## Intent

Every other surface in the app uses the dark-aware
`SECTION_CARD` / `TOOLBAR_CARD` tokens from
`src/kaleta/views/theme.py`, which apply a translucent
slate-800 background in dark mode via the `.k-surface`
class. The Settings page (`src/kaleta/views/settings.py`)
instead uses raw `ui.card().classes("p-6 …")` everywhere —
22 occurrences — so it falls back to Quasar's default
white card. In dark mode this renders as bright-white
panels on a slate-900 page; in light mode the cards lack
the rounded border + soft shadow used elsewhere, so the
page feels visually inconsistent. Captions inside the cards
use `text-grey-6` which is acceptable but not aligned with
the `BODY_MUTED` token used on the rest of the app.

## Scope

- **Replace `ui.card().classes("p-6 …")` on the Settings page
  with `ui.card().classes(SECTION_CARD)`** so the Quasar +
  DARK_CSS rules already in place do the work. The padding
  in `SECTION_CARD` (`p-5`) is one step less than today's
  `p-6`; verify by visual diff that this is acceptable. If
  not, append `p-6` after `SECTION_CARD` to override the
  padding while keeping the surface treatment.
- **Replace `text-xs text-grey-6` hint labels** with
  `BODY_MUTED text-xs` (or simply `BODY_MUTED` if the
  smaller size is acceptable). The `.k-muted` class in
  DARK_CSS already handles dark mode.
- **Tabs strip** (`ui.tabs().classes("w-full")` at line ~77)
  — verify the indicator and labels are theme-aware. Quasar
  tabs are dark-aware out of the box, but the parent
  surface still needs to be a `SECTION_CARD` so the page
  background doesn't show through.
- **Audit each tab body** — General / Appearance / Features /
  Data / History / About. Same pattern: every `ui.card`
  → `SECTION_CARD`; every muted caption → `BODY_MUTED`.
- **Sub-cards inside a tab** (e.g. backup options in Data,
  audit-log rows in History) keep their own `SECTION_CARD`
  but with `p-4` instead of `p-5` so nesting feels
  visually contained.
- **No structural change** to the page logic; this is a pure
  styling pass mirroring the credit dark-mode plan.

Out of scope:
- Re-laying-out the tab order (handled by the UX audit
  plan).
- Renaming i18n keys.
- Changing settings storage shape.

## Acceptance criteria

- Toggle dark mode on `/settings`. Each tab's panels render
  with the same translucent slate-800 surface used on
  /accounts, /transactions, etc.; no bright-white cards
  remain.
- In light mode, the cards display the rounded border and
  soft shadow of `SECTION_CARD`, matching the rest of the
  app.
- All caption labels pass WCAG AA against their card.
- Visual regression: side-by-side screenshots before/after
  on each of the six tabs.

## Touchpoints

- `src/kaleta/views/settings.py` — class swaps; ~22 sites.
- `src/kaleta/views/theme.py` — only consulted; no edits
  expected unless the audit finds a missing token (e.g. a
  smaller `SECTION_CARD_DENSE`).
- No model / migration / i18n / test changes.

## Open questions

1. **Per-tab compactness** — Settings has dense fields
   (toggles, selects). The audit may find `p-5` too tight
   on a single column; widen with `p-6` only where needed.
2. **Tab indicator colour** — verify it's the brand primary
   in both modes; if not, add a DARK_CSS override.
3. **Responsive width** — current cards are `w-80 min-w-72`.
   The fix preserves that constraint; only the
   surface tokens change.

## Implementation notes
_Filled in as work progresses._
