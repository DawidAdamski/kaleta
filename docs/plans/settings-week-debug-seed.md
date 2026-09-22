---
plan_id: settings-week-debug-seed
title: Settings — week-start knob, debug panel, per-feature example data
area: settings
effort: medium
roadmap_ref: ../roadmap.md#settings
status: in-progress
deferred_to: q4-2026
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
- Changing the setting in Settings → General reloads the pages that
  bucket by week with the new bucketing (see Implementation notes: the
  ledger's week grouping is the only such consumer today).
- Unit tests in `tests/unit/core/test_weeks.py` cover at least
  4 month cases (31/30/29/28 days) and both modes.
- `uv run pytest tests/unit/core/test_weeks.py -q`
- `uv run pytest tests/unit/services/test_transaction_service.py -q -k group_separator`

### Debug panel
- With `KALETA_DEBUG=true`, the About tab shows the Debug
  section.
- With debug off, the section is hidden.
- The "Copy debug info" button places a multi-line Markdown
  string on the clipboard.
- Secrets (`SECRET_KEY`, DB password) never appear in the
  debug output.
- `uv run pytest tests/unit/test_debug_info.py -q`

### Example data
- Clicking "Seed everything" on a fresh DB produces at least
  one row in every major table (verified by a smoke test).
- Clicking "Accounts" only creates new accounts and leaves
  other tables alone.
- Rerunning "Seed everything" on a DB that already has seeded
  data does not duplicate rows (seeders are idempotent).
- The CLI `uv run python scripts/seed.py` produces the same
  dataset as the UI "Seed everything" button.
- `uv run pytest tests/unit/seeders -q`
- `uv run pytest tests/integration/test_example_data.py tests/integration/test_seed_payees_tags.py tests/integration/test_seed_payment_calendar.py tests/integration/test_reset_demo.py -q`

### Whole plan
- `uv run python scripts/spec_coverage.py`
- `[manual]` Press every Example-data button on a fresh install and confirm
  each page it fills now has something on it.

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

### Open questions, resolved

1. **Week-start default** — `iso_monday`, the plan's default. `WeekStartMode`
   in `kaleta/core/weeks.py` holds exactly the two modes; anything else in
   storage (an older build, a hand-edited session) falls back to the default
   through `coerce_mode` rather than taking a page down.
2. **Forecast / Prophet bucketing** — untouched, the plan's default.
3. **Debug copy format** — Markdown, the plan's default. One `###` block per
   section, a table for `key: value` rows and a fenced block for log lines.
4. **"Seed everything" on a non-empty DB** — prompt, the plan's default. The
   confirmation dialog names the features that already hold example data with
   their row counts ("Categories, tags & payees (23)"), and the section lists a
   live row count beside every button.
5. **Per-seeder row count** — read as *realistic*, not literally ~40, and this
   is the one place the plan's default was not taken at face value. Two
   reasons: a household has three reserve funds and one credit card, not
   forty; and the transactions seeder is the existing six-year generator,
   which `KAL-PLT-003/004/005` and `scripts/restyle_fidelity.py` both depend
   on (25+ payees with 3+ transactions each cannot come out of 40 rows).
   Counts on a fresh database: 23 categories, 37 payees, 8 tags, 4 accounts,
   3 institutions, 3 assets, ~1600 transactions (72 linked transfer pairs
   among them), 576 budgets, 15 planned transactions, 5 subscriptions,
   3 reserve funds, 3 loans with 3 repayments, 1 credit-card profile.

### What "applied to" turned out to mean (week-start)

Scope §1 lists Budgets, Reports, the Payment Calendar and the dashboard
cashflow chart, with "if they exist — confirm" against the first. Confirmed,
and the answer is narrower than the plan assumed:

- **Budgets and Reports have no weekly bucketing at all.** `report_service`
  works in months, quarters and years; `budget_service` in budget months.
  There was nothing to rebucket.
- **The Payment Calendar's month grid is a calendar, not a bucketing of data.**
  It lays out days in a Monday-first grid; no subtotal is computed per week.
- **The dashboard cashflow chart buckets by month**, not week.
- The one real consumer is the **ledger's `grouping == "week"`**:
  `TransactionService.group_separator_label` decides where a week starts and
  `views.components.transaction_table.attach_group_labels` writes the band over
  it. Both now take a `WeekStartMode` and both call `week_bucket`, so the
  heading and the rows under it cannot disagree. The knob calls
  `ui.navigate.reload()` for the same reason the language knob does: every
  weekly subtotal on screen was computed under the old answer.

`week_bucket` clips month-relative weeks to their month (being inside one month
is what defines them) and does **not** clip ISO weeks (a Monday-to-Sunday week
is seven days wide wherever it is read; trimming it would make a subtotal
disagree with its own heading). That is why October 2025 gives five complete
Monday-to-Sunday weeks under `iso_monday` and `01–07 / … / 29–31` under
`month_day_1`.

**Pre-existing, left alone:** the older `week_start` knob (Monday/Sunday) is
written to storage and read nowhere, and its hint claims it applies to the
Payment Calendar. It is a different knob from `week_start_mode` — first day of
a calendar grid, not how data is bucketed — so fixing it is outside this
plan's scope. Filed for the Chore inbox.

### Debug panel

- `kaleta/debug_info.py` is free of NiceGUI: the view hands in what the session
  holds, so the whole report can be built and asserted on in a unit test.
- **Masking is by name, not by inspection.** A `KALETA_*` name containing
  SECRET, PASSWORD, TOKEN, KEY, DSN or WEBHOOK prints as `***`, and a `*_URL`
  has its password replaced. A secret added to `Settings` next year is
  therefore redacted by default rather than leaking until someone notices.
- **Log lines come from `SessionRingBuffer`, not a file.** The plan asked for
  the tail of `kaleta.log`; no log file is configurable (only `KALETA_LOG_FORMAT`
  and `KALETA_LOG_LEVEL`), and the ring buffer already holds the last 200
  records of the session, redacted on the way in. Last 30 are shown.
- **The scheduler table is omitted**, as the plan allows: there is no scheduler
  until `wizard-reminders` lands.
- Two sections the plan did not ask for and the report is much more useful
  with: the library versions that decide how a bug reproduces, and the
  *settings in force* (defaults included) rather than only the env vars that
  happen to be set.

### Example data

- `kaleta/seeders/` is a registry of ten `Seeder` objects in dependency order.
  Each owns its rows and answers `count` / `create` / `remove`; `Seeder.seed`
  turns that into idempotence — a feature with rows is skipped unless
  `replace=True`. `seed_features(["transactions"])` expands to
  `taxonomy → accounts → transactions`, because a transaction cannot exist
  without an account and a user pressing *Transactions* on an empty database
  means "give me transactions", not "fail".
- `replace` is passed on **only to the features that were asked for**. A
  dependency pulled in behind the scenes is filled if empty and left alone
  otherwise — replacing the accounts because someone replaced the credit-card
  terms would delete a ledger nobody mentioned.
- **`DataService.seed` was a third copy of the generator** — same constants as
  `scripts/seed.py` but without payees, tags, planned transactions,
  subscriptions or any of the newer features. It now wipes and then calls the
  registry, so `scripts/reset_demo.py` and the destructive Settings "Populate
  with example data" button get the full dataset. `clear_all` grew the tables
  the new seeders write (subscriptions, reserve funds, loans, credit-card and
  loan profiles, categorisation rules, dismissed candidates); without them a
  re-seed would have found those features non-empty and skipped them.
- **Faker is gone from the generator.** It is a dev dependency, and the
  seeders ship in the app so the Settings button works on an install that
  never saw the test extras. The five generated fallback merchants became five
  curated Polish ones, which keeps the payee count at 37 and `KAL-PLT-003`
  (25+ payees, 3+ transactions each) satisfied.
- **`scripts/seed.py` no longer drops the tables** by default — it creates what
  is missing and fills in what is empty, so a plain run is the same operation
  the UI button performs. `--fresh` keeps the old drop-and-recreate, `--only`
  seeds named features and `--replace` rewrites them. As a consequence the
  `alembic stamp head` step in `scripts/restyle_fidelity.py` became
  unnecessary (the schema stays at head) and was removed.
- Determinism is what makes `KAL-PLT-008` checkable rather than merely
  described: both generators are pinned to `random.Random(42)`, salted per
  seeder so two seeders do not draw the same sequence while each stays
  reproducible run alone.

### Architecture

- Two new layers in the import-linter contract: `kaleta.core` at the bottom
  (pure helpers, imports nothing of Kaleta's) and `kaleta.seeders` directly
  below `kaleta.services`. **No `ignore_imports` entry was added** — the
  seeders reach models and `kaleta.db` because they sit below services, and
  the views reach them only through `DataService` plus the registry metadata
  the buttons are built from.
- `MissingSeedDependencyError(NotFoundError)` in `kaleta/seeders/lookups.py`
  rather than a bare `RuntimeError`, per the domain-errors convention. It is
  only reachable by calling a seeder directly; the registry seeds
  `depends_on` first.

### BDD

New scenarios, all `@automated` with tests carrying `Covers:`:

| Scenario | Covered by |
|---|---|
| `KAL-SET-027` weekly grouping knob persists | `tests/e2e/test_settings_week_debug.py` |
| `KAL-SET-028` debug panel behind `KALETA_DEBUG` | `tests/e2e/test_settings_week_debug.py` |
| `KAL-SET-029` debug report is Markdown without secrets | `tests/integration/test_example_data.py` |
| `KAL-PLT-006` seed everything fills every feature once | `tests/integration/test_example_data.py` |
| `KAL-PLT-007` seeding one feature leaves the others alone | `tests/integration/test_example_data.py` |
| `KAL-PLT-008` CLI and registry produce the same dataset | `tests/integration/test_example_data.py` |
