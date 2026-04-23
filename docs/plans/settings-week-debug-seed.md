---
plan_id: settings-week-debug-seed
title: Settings — week-start knob, debug panel, per-feature example data
area: settings
effort: medium
roadmap_ref: ../roadmap.md#settings
status: draft
---

# Settings — week-start knob, debug panel, per-feature example data

## Intent

Three small-ish Settings extensions requested while using the app:

1. **Week-start mode** — some users want weeks to start from
   Monday ("full week" ISO), others from the first day of the
   current month ("rolling from day 1" — i.e. day-of-month-based
   weekly groupings). This affects weekly subtotals in Budgets,
   Reports, and Payment Calendar.
2. **Bigger debug panel** in the About tab — when
   `KALETA_DEBUG=true`, show version, env vars, DB URL (masked),
   active feature flags, storage-user keys, scheduler job table,
   recent errors from the log. Helpful for self-debugging and
   issue reports.
3. **Populate with example data** — per-feature seed buttons (or
   a single "Seed everything" button) that insert realistic
   Polish example data for *every* feature the app now has —
   accounts, transactions, budgets, planned transactions,
   subscriptions, reserve funds, personal loans, credit cards.
   Useful for new users, demos, and self-testing.

## Scope

### 1. Week-start mode

- Setting `settings.week_start_mode`:
  - `iso_monday` — weeks run Monday–Sunday (ISO 8601). *Default.*
  - `month_day_1` — first week of a month starts on the 1st; each
    subsequent week is 7 days later; the last stub week can be 1-7
    days depending on month length.
- Applied to:
  - Budgets weekly totals (if they exist — confirm).
  - Reports weekly groupings.
  - Payment Calendar "this week" bubbles.
  - Dashboard cashflow chart weekly bucketing (if used).
- Exposed as a dropdown in Settings → General.
- Stored in `app.storage.user["week_start_mode"]`.
- Tested via a pure helper
  `week_buckets(dates, mode)` in `kaleta.core.weeks` (new module)
  with unit tests covering month boundaries and February leap years.

### 2. About tab debug panel

- Existing About tab under Settings:
  - Version, env, links — keep.
- New **"Debug info"** expansion (only visible when
  `settings.debug is True`):
  - Python version, NiceGUI version, SQLAlchemy version,
    Pydantic version.
  - Active `KALETA_*` env vars (names + redacted values — show
    `DB_URL` with the password replaced by `***`; `SECRET_KEY`
    as `***`).
  - Storage-user keys summary:
    `list(app.storage.user.keys())` with types.
  - Feature-flag summary from the Features tab.
  - Scheduler jobs table (if the scheduler is running from the
    wizard-reminders plan — otherwise omit).
  - Last N log lines (tail of `kaleta.log` if configured,
    otherwise an empty placeholder).
  - "Copy debug info" button → puts everything into clipboard as
    a Markdown block suitable for a GitHub issue.

### 3. Populate with example data

- **Settings → Data** tab: new section **"Example data"**:
  - One button per feature:
    - Accounts, Transactions, Budgets, Planned Transactions,
      Subscriptions, Reserve Funds, Personal Loans, Credit Cards,
      Categories / Tags / Payees.
  - One button **"Seed everything"** at the top — idempotent;
    skips features that already have rows beyond the defaults.
  - Each button confirms via dialog before writing.
- **Per-feature seeder** lives in
  `src/kaleta/seeders/<feature>.py` and exposes
  `async def seed(session, replace: bool = False)`. The
  "Populate" button sets `replace=False`.
- **Script parity** — `scripts/seed.py` becomes a thin wrapper
  that calls each feature seeder in dependency order, so the
  UI and CLI produce the same data.
- **i18n** — every seeder has localisable names for its seed
  rows. Polish is primary (Kaleta's default).

Out of scope:
- Undo for example-data seeding (users can wipe the DB from the
  existing Data tab).
- Custom example-data profiles ("Freelancer", "Student" —
  handled by `categories-templates` which ships templates, not
  sample transactions).
- Cross-feature referential integrity beyond what each seeder
  already handles.

## Acceptance criteria

### Week-start
- With `iso_monday`, a date range `2025-10-01..2025-10-31` has
  five complete weeks from Monday to Sunday (plus stub).
- With `month_day_1`, the same range has weeks
  `01–07 / 08–14 / 15–21 / 22–28 / 29–31` — the final week is
  3 days.
- Changing the setting in Settings → General reloads Reports /
  Budgets / Payment Calendar with the new bucketing.
- Unit tests in `tests/unit/core/test_weeks.py` cover at least
  4 month cases (31/30/29/28 days) and both modes.

### Debug panel
- With `KALETA_DEBUG=true`, the About tab shows the Debug
  section.
- With debug off, the section is hidden.
- The "Copy debug info" button places a multi-line Markdown
  string on the clipboard.
- Secrets (`SECRET_KEY`, DB password) never appear in the
  debug output.

### Example data
- Clicking "Seed everything" on a fresh DB produces at least
  one row in every major table (verified by a smoke test).
- Clicking "Accounts" only creates new accounts and leaves
  other tables alone.
- Rerunning "Seed everything" on a DB that already has seeded
  data does not duplicate rows (seeders are idempotent).
- The CLI `uv run python scripts/seed.py` produces the same
  dataset as the UI "Seed everything" button.

## Touchpoints

### Week-start
- New `src/kaleta/core/weeks.py` with
  `week_buckets(dates, mode) -> list[(start, end)]`.
- `src/kaleta/services/report_service.py`, `budget_service.py`,
  `payment_calendar_service.py` — wire through mode from
  storage.
- `src/kaleta/views/settings.py` — add dropdown.
- `src/kaleta/i18n/locales/{en,pl}.json` — labels.
- `tests/unit/core/test_weeks.py`.

### Debug panel
- `src/kaleta/views/settings.py` — new expansion.
- Helper `src/kaleta/debug_info.py` building the info dict /
  markdown.
- `src/kaleta/i18n/locales/{en,pl}.json` — section labels.

### Example data
- New `src/kaleta/seeders/` package:
  - `__init__.py` — registry.
  - One module per feature.
- Refactor `scripts/seed.py` to delegate to the registry.
- `src/kaleta/views/settings.py` — buttons in Data tab.
- `tests/unit/seeders/test_registry.py` — each seeder is
  idempotent (running twice yields same row count).
- `src/kaleta/i18n/locales/{en,pl}.json` — per-seeder labels.

## Open questions

1. **Week-start default** — `iso_monday` (Polish standard) vs
   `month_day_1`. Default: **iso_monday**.
2. **Does week-start also apply to Forecast / Prophet bucketing?**
   Default: **no** — Prophet uses its own temporal logic; keep it
   untouched.
3. **Debug copy format** — GitHub-flavored Markdown vs JSON.
   Default: **Markdown** (easy to paste into an issue).
4. **"Seed everything" on a non-empty DB** — skip or prompt?
   Default: **prompt**, with a per-feature status ("accounts
   already seeded (12 rows)").
5. **Per-seeder row count** — aim for 30 of each "transaction-
   shaped" entity or 100? Default: **~40** — enough to make charts
   meaningful, not so many that it slows the app.

## Implementation notes
_Filled in as work progresses._
