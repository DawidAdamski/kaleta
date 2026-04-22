---
plan_id: settings-expansion
title: Settings — structured sections and missing knobs
area: settings
effort: medium
status: draft
roadmap_ref: ../roadmap.md#settings
---

# Settings — structured sections and missing knobs

## Intent

Settings is a grab-bag today. Split into clearly labelled sections
and add the knobs users have asked for — most notably locale/currency
defaults and wizard controls.

## Scope

Sections (tabs or anchored groups):
- **General** — language, locale, date format, default currency,
  week-start.
- **Appearance** — theme (light/dark/system), density, sidebar
  default-state.
- **Wizard** — resurface any wizard section that was dismissed, reset
  the "Getting Started" to show again.
- **Privacy & data** — export full data, import backup, wipe local
  DB (with confirmation).
- **About** — version, env, links to docs and GitHub.

Out of scope:
- Multi-user accounts / SSO — not in scope for the single-user app.
- Cloud-sync toggles — handled in a separate plan when that lands.

## Acceptance criteria

- All existing settings migrate to the appropriate section with no
  regression.
- Changing language flips the UI immediately (no reload required).
- Changing default currency only affects *new* accounts/transactions;
  never rewrites existing data.
- "Reset Getting Started" un-dismisses the wizard card.
- Data export produces a single downloadable archive (JSON + CSVs).

## Touchpoints

- `src/kaleta/views/settings.py` — restructure into sections.
- `src/kaleta/services/settings_service.py` — may need split into
  sub-services (appearance, general, data).
- `src/kaleta/config/settings.py` — any new persisted settings.
- `src/kaleta/i18n/locales/*`.
- `app.storage.user` keys — enumerate and document in the module.

## Open questions

- Data export format: JSON + CSV bundle, or SQLite snapshot? v1:
  JSON + CSVs for portability.
- Wipe-DB gesture: require typing the word "DELETE" to confirm.

## Implementation notes

_(filled as work progresses)_
