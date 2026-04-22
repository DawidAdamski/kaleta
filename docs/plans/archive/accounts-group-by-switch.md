---
plan_id: accounts-group-by-switch
title: Accounts "Group by" as toggle switch
area: accounts
effort: small
status: archived
archived_at: 2026-04-22
roadmap_ref: ../roadmap.md#accounts
---

# Accounts "Group by" as toggle switch

## Intent

Make grouping on the Accounts page feel instant. Today it is a
dropdown; the user wants a two-option switch where clicking the
opposite option snaps to it without a menu step.

## Scope

- Replace `ui.select` used for "Group by" with a `ui.toggle`
  (or chip-style equivalent) exposing Type and Institution.
- Both options visible at once; a single click toggles state.
- State stays persisted per user.

Out of scope:
- Adding a third grouping (e.g. Currency). If/when added, re-evaluate
  whether a toggle is still the right control or a chip group is
  needed.

## Acceptance criteria

- Clicking **Type** when Institution is active groups by Type.
- Clicking **Institution** when Type is active groups by Institution.
- No menu opens on click; UI reflects the change immediately.
- Selection is persisted in `app.storage.user` and restored on reload.
- Dark mode palette respected (matches other toggles in the app).

## Touchpoints

- `src/kaleta/views/accounts.py` — replace the select control.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — labels already
  likely exist; verify `accounts.group_type`, `accounts.group_institution`.

## Open questions

- Does NiceGUI's `ui.toggle` render cleanly with two named options in
  dark mode? If not, use a chip group (`ui.button_group` of two
  buttons with active-state styling).

## Implementation notes

_(filled as work progresses)_

## Implementation

Landed on 2026-04-22.

| SHA | Author | Date | Message |
|---|---|---|---|
| `4317f40` | Dawid | 2026-04-22 | feat: dashboard command center, reports library, forecast presets, and plan-driven features |

**Files changed:**
- src/kaleta/views/accounts.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
