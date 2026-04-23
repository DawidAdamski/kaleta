---
plan_id: settings-expansion
title: Settings — structured sections and missing knobs
area: settings
effort: medium
status: archived
archived_at: 2026-04-23
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

## Implementation

Landed on 2026-04-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `358556f` | Dawid | 2026-04-23 | feat(settings): tabbed layout + per-feature knobs |

**Files changed:**
- `src/kaleta/views/settings.py`
- `src/kaleta/views/subscriptions.py`
- `src/kaleta/views/housekeeping.py`
- `src/kaleta/views/payment_calendar.py`
- `src/kaleta/services/subscription_service.py`
- `src/kaleta/services/dedupe_service.py`
- `src/kaleta/i18n/locales/en.json`
- `src/kaleta/i18n/locales/pl.json`
- `docs/architecture.md`
- `docs/tech-stack.md`
- `README.md`

**What shipped:**
- **6 tabs**: General, Appearance, Features, Data, History, About. Tab state preserved by Quasar; each tab body renders only its own content.
- **General**: language (existing), default currency (existing), date format (ISO/EU/US — persisted as `date_format`), week start (Monday/Sunday — persisted as `week_start`).
- **Appearance**: theme toggle (mirrors the header `dark_mode` key), sidebar default state (`sidebar_mini`).
- **Features**: Reset Getting Started button (clears `wizard_mentor_dismissed`, re-opens `wizard_onboarding_open`); three runtime knobs — Subscriptions detector window, Housekeeping duplicate scan window, Payment Calendar overdue window — with sensible min/max bounds.
- **Data**: exchange rates (kept from previous layout), backup/restore, seed, wipe now requires typing DELETE exactly to confirm (plan's open-question default).
- **History**: audit log (unchanged, moved to its own tab).
- **About**: runtime mode, debug flag, host, port, GitHub + Documentation link buttons.
- **Service surface extended**: `SubscriptionService.detect_candidates(window_days=...)` and `DedupeService.duplicate_transactions(window_days=...)` accept a runtime parameter. `PlannedTransactionService.grid_for_month` already had `overdue_window_days`; the Payment Calendar view now feeds it from user settings.
- **Module docstring on `settings.py`** enumerates every persisted `app.storage.user` key and its meaning — the documented-keys list the plan asked for.

**Partial coverage / deferred:**
- **Language-change live flip without reload** — plan asked for immediate language switch; today it triggers `ui.navigate.reload()` like other settings. Live re-rendering would require a deeper i18n refactor (every view reading from a reactive source).
- **`date_format` applied everywhere** — the setting is persisted and documented, but existing pages still use hard-coded `strftime` patterns. Migration to a central `format_date()` helper is a follow-up.
- **`week_start` applied in Payment Calendar** — persisted but not yet reflected in the calendar grid (would require reordering `_WEEKDAY_KEYS` based on the setting).
- **Data export format** — plan called for "JSON + CSVs archive"; v1 keeps the existing backup zip (same as before), which ships as a single downloadable archive. Not the exact JSON-plus-CSV form the plan described.
- **Wizard reset also un-dismissing per-section cards** — partial: clears `wizard_mentor_dismissed` (mentor suggestions) and re-opens the onboarding panel. Per-section dismissals of other wizard panels (if any) are not surfaced here.
- **Density preference** — plan mentioned density (compact/comfortable); not shipped. Adding this cleanly would require a theme refactor to apply density tokens globally.
- **Multi-user accounts / SSO / cloud-sync** — already out of scope per plan.
