---
plan_id: transactions-upcoming-planned
title: Transactions — show upcoming planned items (next N days)
area: transactions
effort: medium
roadmap_ref: ../roadmap.md#transactions
status: in-progress
deferred_to: q4-2026
---

# Transactions — show upcoming planned items (next N days)

## Intent

The Transactions list shows past actuals only. Users wanting a
quick "what's coming" view have to switch to /payment-calendar
or /planned-transactions. Render upcoming `PlannedTransaction`
occurrences for the next **N days** (user-configurable, default
**7**, alternative **30**) inline with the actuals, visually
distinguished as planned, so the user gets a single
chronological feed of past + near-future cashflow without
leaving the page.

## Scope

- **Settings — new field** in the Settings → Features tab
  (`views/settings/features_tab.py`):
  - Label: "Show upcoming planned transactions". Options:
    `Off / 7 days / 30 days`. Default: `7 days`.
  - Persisted in `app.storage.user["transactions_upcoming_days"]`
    (NiceGUI per-user storage; matches existing pattern of
    other Features-tab toggles).
- **View — Transactions list** (`views/transactions/page.py`):
  - On page load, read the setting; if non-zero, call
    `PlannedTransactionService.get_occurrences(today,
    today + N days)` and merge into the rendered rows.
  - Insert occurrences at the top of the list (newest-first
    ordering already used; planned occurrences have future
    dates so they naturally land at the top after the sort).
  - Mark each planned row visually:
    - Faded / italic typography (Tailwind `italic
      text-slate-500` or a `.k-planned-row` class).
    - Right-side `ui.chip(t("transactions.planned_chip"),
      icon="schedule")` so the user can tell.
    - Date column shows the relative phrase
      ("In 3 days · Wed 14") in addition to the raw date.
  - Clicking a planned row opens the PlannedTransaction
    detail dialog (existing `/planned-transactions` edit
    flow), not the Transaction edit dialog.
  - **"Post / convert to actual" is out of scope here.** That
    behaviour is owned by
    [`planned-transactions-post-due.md`](archive/planned-transactions-post-due.md).
    After that plan ships, a thin follow-up may add a row-level
    Post button that calls the shared service — do not implement
    posting logic in this plan.
- **Sorting / filtering** — the existing filter bar (date
  range, account, category, type, description) applies to
  planned occurrences as well. Account / category / type /
  description filters: re-use the same predicates against
  `PlannedOccurrence`. Date-range filter: clip the upcoming
  window to the user's chosen range.
- **i18n** — `transactions.planned_chip`,
  `transactions.upcoming_section_label` (if a section header
  is preferred over inline interleaving),
  `transactions.upcoming_in_days_label`,
  `settings.show_upcoming`, `settings.show_upcoming_hint`,
  `settings.show_upcoming_off`, `settings.show_upcoming_7`,
  `settings.show_upcoming_30`.
- **Tests** —
  - Unit: helper that merges actuals + occurrences and
    re-sorts.
  - Integration: with a planned monthly rent due on day 5,
    `today = day 3`, `N=7` shows 1 planned row; `N=30` may
    show 2 (this month's and next month's, depending on
    calendar).
  - Settings round-trip: change setting, reload, verify
    storage persistence.

Out of scope:
- Editing the planned-transaction template from the
  Transactions list. The row click opens the detail dialog
  in read-only "next occurrence" mode.
- Auto-hiding planned rows once their date passes (the
  service already filters by `today` so this is automatic).
- Confirming a posted occurrence as "skipped" — that's
  handled on the planned-transactions page.
- Showing planned rows in the CSV export.
- Posting / converting an occurrence to a real
  `Transaction` — see
  [`planned-transactions-post-due.md`](archive/planned-transactions-post-due.md).

## Acceptance criteria

- Setting `transactions_upcoming_days = 7`: a planned weekly
  expense due in 3 days appears as a row in /transactions,
  italicised, with a `schedule` chip and the date "In 3 days".
- Setting set to `0` (Off): no upcoming rows appear; the
  page renders identically to today.
- Filtering by account hides planned rows from other
  accounts.
- Clicking a planned row opens the planned-transaction
  detail dialog — read-only, per "Out of scope" below — and
  not the regular transaction dialog. (Reworded during
  implementation: the original criterion said "edit dialog",
  which contradicted this plan's own binding out-of-scope
  line. See Implementation notes.)

## Touchpoints

- `src/kaleta/views/settings/features_tab.py` — Features tab
  gains the new tri-state toggle.
- `src/kaleta/views/transactions/page.py` — fetch + merge upcoming
  occurrences; row rendering tweaks; row click handler.
- `src/kaleta/services/planned_transaction_service.py` —
  `get_occurrences()` reused as-is; two thin read helpers added
  on top of it (`upcoming_window`, `upcoming_for_ledger`) plus
  the row builder. No post/convert helpers.
- `src/kaleta/i18n/locales/{en,pl}.json` — new keys.
- Also touched, all accounted for in Implementation notes:
  `services/transaction_service.py` (the merge, and the net that
  skips promises), `views/transactions/planned_dialog.py` (new —
  the read-only detail dialog),
  `views/components/transaction_table.py` (the planned row's
  rendering and its relative-date label),
  `views/settings/constants.py` + `views/settings/user_prefs.py`
  (the new key and its reader), `views/theme.py`
  (`.k-planned-row`, `.k-planned-chip`, `.k-upcoming-when`),
  and `tests/e2e/ledger.py` (shared filter helpers).
- `tests/unit/services/test_planned_transaction_service.py`
  and a new `tests/integration/test_transactions_upcoming.py`
  (`tests/integration/` has no `views/` package; the file sits
  beside its siblings rather than creating one).

## Open questions

1. **Inline merge vs separate "Upcoming" section?** Default:
   **inline merge** — the user thinks chronologically; a
   separate section forces a context switch. Visual fade +
   chip is enough to disambiguate.
2. **Default value** — `7 days` strikes a balance: long enough
   to plan the week, short enough not to pollute the list.
3. **Server-side vs client-side merge?** Server-side. Generating
   occurrences in Python keeps the existing service and lets
   the API return them too.
4. **Group separators** — the existing month/week separator
   logic should treat planned rows as ordinary rows for the
   purpose of grouping; verify in tests.

## Implementation notes

### Open questions — decisions taken

1. **Inline merge**, as the plan's default. `TransactionService.merge_upcoming_rows`
   concatenates and re-sorts newest-first; on a day holding both, the recorded
   rows come before the promised ones.
2. **Default 7 days**, as the plan's default. Stored under
   `app.storage.user["transactions_upcoming_days"]`; only `0 / 7 / 30` are
   honoured (`get_transactions_upcoming_days` falls back to 7 for anything
   else), so a value left by an older build cannot open an arbitrary window.
3. **Server-side merge**, as the plan's default. The service produces the rows;
   `attach_upcoming_labels` in the view component adds the locale sentence.
4. **Group separators are recomputed over the merged list.** They are worked
   out from the actuals alone in `build_table_rows`, so a planned row that
   opens a week or a month of its own would otherwise carry no label and the
   first actual would keep a stale one. Covered by
   `TestMergeUpcomingRows::test_the_separators_of_the_actuals_are_worked_out_again`.

### Decisions the plan did not name

- **The search filter matches the plan's `name`,** where the ledger's search
  matches `Transaction.description`. They line up on screen because an
  upcoming row's description cell *is* the plan name (`occ.name[:55]`), so one
  search box narrows both kinds of row the same way.

- **Posted occurrences are excluded** (`exclude_posted=True`). The ledger
  already holds the real transaction for them; showing both would count the
  same money twice by eye. KAL-PLN-023.
- **Upcoming rows are left out of the group net and the selection total.**
  `net_of_rows` now skips `is_planned` rows for the same reason it skips
  transfers: the money has not moved. The `transactions.group_net` tooltip was
  reworded in both locales to say so. KAL-PLN-024.
- **A planned row is not selectable.** Its id is the string key
  `planned:<plan_id>:<ISO date>`, which names no transaction — the selection
  bar deletes by id, so planned rows are kept out of `page_rows` and their
  checkbox is not rendered.
- **Upcoming rows ride on the first page only** (`filters["page"] == 0`), and a
  tag filter suppresses them entirely — a plan carries no tags, so none could
  match. Repeating them under every page number would promise the same money
  once per page.
- **The window starts today, never earlier.** Overdue occurrences belong to the
  Payment Calendar's overdue strip (KAL-PLN-020), not to the ledger.
- **The row click opens a read-only detail dialog**
  (`views/transactions/planned_dialog.py`), per the plan's "Out of scope:
  editing the planned-transaction template from the Transactions list". The
  dialog reads the plan out and offers a button through to `/planned` rather
  than a second editor that could drift from the first.

### Deviations from the plan's wording

- **The date cell reads "In 3 days" under the `dd.mm` short date, without a
  weekday.** The plan sketched "In 3 days · Wed 14"; the ledger's date column
  is 95px and already carries the full ISO date in a tooltip, so a weekday
  would have to buy its space from the description column. The relative phrase
  is the part the reader was after.
- **"7 days" means today through today + 7,** eight calendar days inclusive.
  The alternative — stopping at today + 6 — would make a plan due a week today
  invisible under the setting named for it.
- The integration test landed at `tests/integration/test_transactions_upcoming.py`
  (see Touchpoints).
- When the filters match no recorded rows but some upcoming ones, the count
  under the table says so (`transactions.upcoming_only_*`) instead of "No
  transactions match your filters" sitting under visible rows.

### Review follow-ups

- `upcoming_window` was moved out of `views/transactions/page.py` and onto
  `PlannedTransactionService`, so the window rule sits with the rest of the
  occurrence logic rather than in a view.
- The acceptance criterion about the row click said "edit dialog" while the
  plan's own "Out of scope" asked for read-only. The out-of-scope line is
  binding, so the criterion was reworded to agree with it; the behaviour did
  not change.
- A plan deleted between the page being drawn and the row being clicked now
  raises a toast (`transactions.planned_gone`) instead of a click that does
  nothing. KAL-PLN-025 stages exactly that race, deleting the plan behind the
  browser's back through the new `delete_planned_transaction` seed helper.
- A group made only of upcoming rows shows no net at all rather than `0.00`:
  `0.00` would claim the month came out even, which is a different statement
  from "nothing is recorded in it yet". A group of transfers still reads
  `0.00`, because there nothing really did leave the user
  (`TransactionService.group_net_label`).
- `tests/e2e/ledger.py` gained `pick_open_menu_option` (moved verbatim out of
  `tests/e2e/test_transactions.py`, where it was private) and
  `filter_ledger_by_account`. The new account-filter scenario needs the same
  virtual-scroll handling, and a second copy of it would be the worse answer.

- `PlannedTransactionService` imports `TransactionService` for the two amount
  formatters, so a row's figure is signed and formatted by the one rule the
  ledger uses. The dependency runs one way only — `TransactionService` knows
  nothing about plans — so there is no import cycle to break.
- The `planned:<id>:<date>` row key is built *and* parsed in the service
  (`planned_row_key` / `parse_planned_row_key`), so the format the browser
  hands back is defined in one place rather than split across two layers.

- The plan's prose calls the planned-transactions page
  `/planned-transactions`; the route is and stays `/planned`. The dialog's
  button and KAL-PLN-022 use the real one.
- The occurrence date in the detail dialog is printed ISO, matching the
  ledger's own date tooltip. The `date_format` setting in Settings → General
  is written but not yet read by any view, and making this dialog its first
  consumer is outside the plan's scope.
- The cadence sentence ("Monthly", "every 2 × Weekly") is
  `views/planned_transactions.freq_label`, made public rather than copied, so
  the dialog and the Planned Transactions page cannot end up spelling one
  plan's cadence two ways.

- The table keeps `selection=multiple`, so the header's select-all still ticks
  planned rows even though they render no checkbox. `_on_selection` drops them
  and hands the table back the rows it may keep, so the header cannot claim a
  selection the bar underneath is not counting.
- The two searches fold case differently: the ledger's runs as SQLite `ILIKE`,
  which is ASCII-only, while the plan-name match is Python `lower()`, which is
  not. Typing `ż` finds a planned row spelled `Ż` and does not find a recorded
  one. The planned side is the more forgiving of the two, so it was left
  alone rather than crippled to match — worth an inbox line if the ledger's
  own search is ever made Unicode-aware.

- `search_ledger` now waits for the filter chip's menu to close before it
  returns. The menu overlays the table it just filtered, so a test that clicks
  a row straight after typing could land on the menu and wait out Playwright's
  actionability timeout. KAL-PLN-022 and KAL-PLN-025 both click a row, and
  KAL-PLN-025 caught it intermittently.

- The two row builders are separate, so an integration test pins the planned
  row's key set as a superset of the recorded row's. The table's body slot
  reads one set of fields for both, and a key added to one and forgotten on
  the other would render blank rather than fail.

### Verification

`./scripts/verify.sh --e2e` green on the branch: ruff, ruff format, mypy,
import-linter (4 contracts kept), 2293 unit + integration tests, spec coverage
(324 scenarios, 205 covered), doc links, SPDX, and 160 e2e. The e2e suite was
then run three more times end to end, all green, to confirm the
`search_ledger` fix above settled the flake it exposed.


### BDD

`KAL-PLN-011` and `KAL-PLN-012` described a "Show planned" toggle on the
Transactions page itself; both were rewritten around the Settings knob this
plan specifies, and `KAL-PLN-011` moved from `@manual` to `@automated`.
`KAL-PLN-021…024` and `KAL-SET-026` are new.

### Test-environment note

The e2e suite assumes the documented `uv sync --group dev` environment. With
the optional `forecast` extra (Prophet) also installed, seven pre-existing e2e
tests fail on `main` as well — six in `test_forecast.py` (the forecast never
settles inside the 60s budget) and
`test_wizard_scenarios.py::test_the_panel_works_without_prophet`, which asserts
the extra is absent. Nothing on this branch touches them.
