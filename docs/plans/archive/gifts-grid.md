---
plan_id: gifts-grid
title: Gifts as a yearly grid — people by occasions, amounts in the cells
area: wizard
effort: medium
status: archived
archived_at: 2026-11-12
roadmap_ref: ../../roadmap.md
---

# Gifts as a yearly grid — people by occasions, amounts in the cells

## Intent

The owner plans gifts in a spreadsheet: one row per person, one column per
occasion (Birthday, Name day, Christmas, Easter, St Nicholas' Day, Other —
"Other" holds wedding anniversaries and the like), an amount in each cell, and
totals per row, per column and for the year. That total is the answer to "how
much money do I need for gifts this year".

Today's `/wizard/gifts` is a flat list of "person · occasion · amount" entries
typed as free text and grouped by person (KAL-GFT-001). It cannot show the
grid, a person with no gifts yet, or an occasion column, and every new year
means typing everything again. This plan replaces it with the grid. The yearly
total keeps feeding the Irregular Expenses Fund (KAL-GFT-002).

Decisions already made by the owner (2026-11-11):

- **Columns are occasions shared by everyone**, not per-person dates. The six
  above are the defaults; the user can add, rename and remove occasions
  ("we will be adding people and holidays").
- **One grid per year.** A new year starts as a copy of the previous one.
- **Start from zero.** The old `gifts` rows are not migrated (dogfood data).

## Scope

In scope:

1. **Models** (new revision; the old `gifts` table is dropped):
   - `GiftPerson` (`gift_people`): `name` (encrypted, like today's
     `person`), `position` for row order, `archived` (a person removed from
     the grid keeps the history of past years).
   - `GiftOccasion` (`gift_occasions`): `name` (encrypted), `position`,
     `archived`. Each user gets the six default occasions, created on first
     use of the page, not by the migration (tenants are per family schema).
   - `GiftCell` (`gift_cells`): `year`, `person_id`, `occasion_id`, `amount`
     (`Numeric(15,2)`, ≥ 0), optional short `note` (encrypted), unique on
     (`year`, `person_id`, `occasion_id`). An empty cell is a missing row,
     not a zero.
   - `Transaction.gift_id` is repointed at `gift_cells.id` (`SET NULL`), so
     "bought" (KAL-GFT-003) keeps working, per cell.
2. **`GiftService`** rewritten over the three tables:
   - people/occasions: add, rename, reorder, archive;
   - `set_cell(year, person_id, occasion_id, amount | None)`: `None` or empty
     deletes the cell;
   - `grid(year) -> GiftGrid`: rows, columns, cells, row totals, column
     totals and the yearly total; archived people/occasions appear only in
     years where they have cells;
   - `copy_year(from_year, to_year)`: copies amounts, never "bought" links;
     refuses (`ConflictError`) when the target year already has cells;
   - `summary()` keeps its contract for the irregular fund: the current
     year's total.
   - Typed errors from `kaleta.exceptions`, i18n keys in en/pl.
3. **Page `/wizard/gifts`** (same URL, same nav entry):
   - a year switcher (previous / next); an empty year offers
     "Copy from <year − 1>";
   - the grid: a sticky first column of people, one column per occasion, an
     editable amount per cell (saved on blur/Enter), a row total column, a
     column totals footer, the yearly total in the header;
   - "Add person" / "Add occasion" inline; rename, reorder and archive from
     the row or column header menu;
   - a cell's menu: link a transaction ("bought", with the actual cost)
     or unlink it, as today's dialog does;
   - all strings through `t()`; works at phone width (the grid scrolls
     sideways inside its card, the page does not).
4. **No API.** There is no `api/v1/gifts` today, and this plan adds none.
5. **Everything that touched `Gift`**: `data_service` export/import,
   `dedupe_service` link transfer, the gifts seeder (Polish example data:
   Mama, Tata, Ania; the six occasions; amounts for the current year),
   `irregular_item_service`.
6. **BDD:** KAL-GFT-001 rewritten for the grid; new scenarios for the totals,
   copying a year and adding an occasion; KAL-GFT-002/003 updated to "cell".

Out of scope:

- When in the year the money is needed (occasion dates, a monthly
  breakdown); see Open questions.
- Gift ideas, wish lists, reminders.
- Migrating the old `gifts` rows.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_gift_service.py -q`
- `uv run pytest tests/integration/test_gift_grid.py -q`
- `uv run pytest tests/integration/test_irregular_fund.py -q`
- `uv run pytest tests/e2e/test_gifts.py -q`
- Migration parity: `test_the_migration_builds_what_the_models_declare` in
  `tests/integration/test_gift_grid.py` (run by the second criterion); see
  Implementation notes for why it replaces `uv run alembic check`.
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `grep -q "KAL-GFT-004" docs/bdd.md`

Scenario literals (Working Agreement rule 11), to be written into
`docs/bdd.md`:

- Grid: people Mama and Tata; Mama — Birthday 200.00, Christmas 150.00; Tata —
  Christmas 100.00. Row totals 350.00 and 100.00; Christmas column 250.00;
  year total 450.00.
- Copy: 2026 as above, 2027 empty → "Copy from 2026" → 2027 total 450.00, and
  no cell in 2027 is marked bought even if 2026's Birthday was.
- Occasion: adding "Rocznica ślubu" adds an empty column; the totals do not
  change until an amount is typed.
- Fund: with the 2026 grid above, the Irregular Fund shows "Gifts" 450.00.

## Touchpoints

- `src/kaleta/models/gift.py` (rewrite), `models/transaction.py` (FK
  target), `models/__init__.py`; one new Alembic revision
  (`migration-creator`)
- `src/kaleta/schemas/gift.py`, `services/gift_service.py`,
  `services/irregular_item_service.py`, `services/data_service.py`,
  `services/dedupe_service.py`, `seeders/gifts.py`
- `src/kaleta/views/gifts.py`, `i18n/locales/en.json` + `pl.json`
  (minimal diff)
- tests: `tests/unit/services/test_gift_service.py`,
  `tests/integration/test_gift_grid.py` (new), `test_irregular_fund.py`,
  `test_dedupe_merge_links.py`, `test_example_data.py`,
  `tests/e2e/test_gifts.py`, `tests/e2e/seed_helpers.py`
- `docs/bdd.md` (Gift Planning), `docs/architecture.md` if the model list is
  there

## Open questions

- **When is the money needed?** The owner's answer to "should occasions have
  dates" was the column list, not a yes or no. Default: no dates in this
  plan; the yearly total is what the fund needs. A follow-up can give fixed
  occasions a month (Christmas: December, St Nicholas: December, Easter:
  computed) and people optional birth and name dates, for a monthly view.
- **Note per cell.** Default: yes, short and optional. It is what "Other"
  needs ("Other: anniversary").
- **Columns per year?** Default: occasions are shared across years; an
  occasion archived in 2027 still shows in 2026.
- **Who is a person?** Default: free text, not linked to Kaleta's payees or
  household members.

## Implementation notes

- **Branch.** `plan/gifts-grid` is stacked on `chore/e2e-ledger-pref-leak`
  (two test-only commits that stop `test_settings_ledger_defaults` leaking
  Month grouping into every later ledger e2e test). Without them the gate's
  `verify.sh --e2e` fails on that leak, not on this plan. Merge the chore PR
  first; this PR's diff then shrinks to the plan's own commits.
- **`alembic check` → a parity test.** `uv run alembic check` cannot run here:
  it connects to the default `localhost:5432` and needs a family schema at
  head (the same finding as `archive/gifts-list.md`). Its intent, "the
  migration builds what the models declare", is now an executable test:
  `test_the_migration_builds_what_the_models_declare` reads the suite family's
  schema (built by the real migrations) and compares every column and its
  nullability with the three models, checks the one-cell-per-slot unique
  constraint, that `gifts` is gone, and that `transactions.gift_id` points at
  `gift_cells` with `ON DELETE SET NULL`.
- **Migration.** One new revision (`d4f2a9c61e07`). It clears
  `transactions.gift_id` with a Core `UPDATE` (not `text()`, which would skip
  `schema_translate_map`), drops `gifts` and creates the three tables. The
  old `ix_gifts_user_id` was already dropped by `9f318d21f98a`.
  The downgrade drops the grid and recreates an empty `gifts` table.
- **Default occasions** are created by `GiftService.ensure_default_occasions`
  on the first page load, from `gifts.default_occasions.*` in the user's
  language (en: Birthday, Name day, Christmas, Easter, St Nicholas' Day,
  Other; pl: Urodziny, Imieniny, Boże Narodzenie, Wielkanoc, Mikołajki, Inne).
  Archived occasions count, so removing every default does not bring them
  back.
- **Open questions, defaults taken.** No dates or monthly view. A short,
  optional note per cell (shown as the cell's tooltip). Occasions are shared
  across years. A person is free text, not a payee or household member.
- **Names.** A live person (or occasion) name cannot repeat,
  case-insensitively (`ConflictError`, `errors.gift.name_taken`). An archived
  name can be reused. Names are encrypted, so this check runs in Python.
- **`summary()`** keeps its name and its role for the irregular fund. It now
  returns one year's total (`GiftsSummary(year, yearly_total)`, this year by
  default), so last year's grid does not inflate the fund (KAL-GFT-002, new
  integration test).
- **Bought, per cell.** Linking, unlinking and the picker work as before, on a
  cell id. Emptying a bought cell deletes it, and `ON DELETE SET NULL` frees
  its expense for another gift. Copying a year never copies links.
- **Page.** The view is a `GiftGridPage` class. Typing an amount saves on the
  input's change (blur, Enter or Tab) and updates the row, column and year
  totals in place, without redrawing, so Tab moves on to the next cell.
  Adding, renaming, moving or removing a person or occasion, a note, a bought
  mark and a copied year reload the page. The grid is a `<table>` inside a
  horizontally scrolling card with a sticky first column, so on a phone the
  grid scrolls, not the page. The occasion columns show even before the first
  person is added.
- **No API**: there is no `api/v1/gifts` today (scope point 4).

- **Removed assertions in `test_gift_service.py` (rule 4).** The old file
  tested the flat `Gift` list (create/update/delete a gift row, its
  `occasion`/`date`/`status` fields), and that model and table no longer
  exist. The file is rewritten, not loosened: 34 tests over the grid — lanes,
  cells, totals, copy-a-year and bought-per-cell — with BDD literals.
- **Unrelated flake on the gate's re-run.** One gate run failed on
  `test_wizard_action_service.py::TestPerformance` (216 ms vs a 200 ms
  wall-clock limit) while the machine's load average was ~32 from other apps;
  that test is untouched by this branch and passes alone (0.74 s run). Left as
  is (no raised limit) and logged in `chores.md`.

## Implementation

Landed on 2026-11-12 (PR #415).

| SHA | Author | Date | Message |
|---|---|---|---|
| `88d93c5c` | Dawid Adamski | 2026-11-12 | Merge pull request #415 from DawidAdamski/plan/gifts-grid |

**Files changed:**
- alembic/versions/d4f2a9c61e07_gift_grid.py
- docs/bdd.md
- docs/plans/README.md
- docs/plans/chores.md
- docs/plans/gifts-grid.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/models/__init__.py
- src/kaleta/models/gift.py
- src/kaleta/models/transaction.py
- src/kaleta/schemas/gift.py
- src/kaleta/seeders/gifts.py
- src/kaleta/services/data_service.py
- src/kaleta/services/gift_service.py
- src/kaleta/views/gifts.py
- tests/backup_helpers.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_gifts.py
- tests/integration/test_dedupe_merge_links.py
- tests/integration/test_error_i18n_funds_cohort.py
- tests/integration/test_example_data.py
- tests/integration/test_gift_grid.py
- tests/integration/test_irregular_fund.py
- tests/unit/seeders/test_registry.py
- tests/unit/services/test_gift_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
