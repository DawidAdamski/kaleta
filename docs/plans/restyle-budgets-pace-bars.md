---
plan_id: restyle-budgets-pace-bars
title: Restyle — Budgets/Realization pace bars with month-elapsed tick (artboard 2b)
area: budgets
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#budgets
---

# Restyle — Budgets/Realization pace bars with month-elapsed tick

## Intent

`views/budgets/realization.py` ends every row with a coloured status
word (`STATUS_LABEL_KEY` / `STATUS_COLOUR`). Artboard `2b` replaces it
with a **pace bar**: a track filled to `used_pct`, coloured by the same
threshold the status already uses, and a tick at *percent of month
elapsed*. At 10 % elapsed and 115 % spent, Żywność explains itself with
no legend. Two rows gain a one-line explanation under the bar ("Paid in
full on the 1st — expected", "284,00 zł planned for the 12th") drawn
from planned transactions — this removes most false alarms.

Depends on `restyle-theme-tokens` (`.k-pace*` classes).

## Scope

- **Pace bar** in `render_realization_row`: replace the status badge
  with `.k-pace` (7px track) + `.k-pace__fill` (width
  `min(used_pct, 100)%`, colour income / warning / expense mapped from
  `CategoryRealization.status`) + `.k-pace__tick` at
  `elapsed_pct` (already on the dataclass). Status text moves to a
  tooltip on the bar (keeps the i18n keys). Column header
  `col_status` → `col_pace`.
- **Explanation line** (new computation, service layer): for each
  category, `BudgetService` looks up planned occurrences in the month
  (existing planned-transaction service) and returns an optional
  `explanation: RealizationNote | None` on `CategoryRealization`:
  `paid_in_full_on(day)` when actual ≥ planned and a single planned
  occurrence covers it; `planned_on(amount, day)` when a future
  occurrence in the month exists and used_pct is under 100. Render as a
  12px muted line under the bar. Pure function, unit-tested.
- Row typography: category in ink 13.5px, planned/actual/remaining in
  `k-amount`, `used_pct` in `k-mono`.
- Keep: the four summary KPIs, flat/by-parent toggle, Overview tab.
- i18n keys: `budgets.realization.col_pace`,
  `budgets.realization.note_paid_in_full`,
  `budgets.realization.note_planned_on`.
- BDD: `KAL-BUD-012` "realization row explains an expected early
  payment" (@automated via unit test on the service note).

Out of scope: threshold values (`REALIZATION_WARNING_THRESHOLD_PCT`
unchanged); the Overview tab chart; budget editing.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_budget_service.py -q`
- `uv run pytest tests/e2e/test_budget_vs_actual.py -q`
- `grep -q "k-pace" src/kaleta/views/budgets/realization.py`
- `grep -q "KAL-BUD-012" docs/bdd.md`
- `grep -q "note_planned_on" src/kaleta/i18n/locales/pl.json`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` Seed data, current month: every row shows a bar with a tick
  at the month's elapsed position; an over-budget row is terracotta past
  the tick; a rent-style row shows "Paid in full on the 1st — expected".
  Compare to artboard `2b`, light and dark.

## Touchpoints

- `src/kaleta/views/budgets/realization.py`, `constants.py`
- `src/kaleta/services/budget_service.py` (`CategoryRealization` +
  note computation)
- `src/kaleta/services/planned_transaction_service.py` (read-only use)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `tests/unit/services/test_budget_service.py`,
  `tests/e2e/test_budget_vs_actual.py`

## Open questions

1. Should the note also consider posted planned occurrences (already
   converted to transactions) or only the planned schedule? Default:
   **schedule only** — occurrences carry the day; matching posted
   transactions is a heuristic that belongs in a later plan.
2. Tick when viewing a past month? Default: **tick at 100 %** (month
   fully elapsed) and no note.

## Implementation notes

### Read this before reviewing the diff

Stacked on `plan/restyle-transactions-filter-chips`, itself on
`plan/restyle-dashboard` and `plan/restyle-theme-tokens` — none merged yet.
The declared dependency is only on the theme tokens (`.k-pace*`), but the
branches below carry the e2e race fixes without which `verify.sh --e2e` is
not reliably green on any branch. This plan's own diff is:

    git diff plan/restyle-transactions-filter-chips...HEAD

and its PR is opened with `--base plan/restyle-transactions-filter-chips`,
to be merged after the three below it.

### Open questions — decisions taken

1. **Schedule only, not posted occurrences.** The note reads
   `PlannedTransactionService.get_occurrences` for the month and nothing
   else. Matching a posted transaction back to the occurrence that predicted
   it is a heuristic (amount and date both drift), and getting it wrong turns
   an explanation into a lie.
2. **A past month gets a tick at 100 % and no note** — `elapsed_pct` was
   already 100 there. Extended one step: notes are computed only when *today*
   falls inside the month being viewed. A note explains pace, and a month
   that has not started has no pace to explain either.

### The note is a pure function, and it says very little

`realization_note` returns something in exactly two cases, both of them
cases where the bar on its own misleads:

- **Paid in full.** Exactly one planned occurrence in the month, its amount
  at least the budget, and the money has gone out. Rent leaves on the 1st,
  so its bar is full on the 2nd — that is not an overspend, it is the only
  thing that was ever going to happen.
- **Planned on.** Still under budget, with the nearest occurrence still
  ahead. A category whose bill falls on the 20th reads as underspent all
  month for no reason at all.

Two occurrences do not count as a bill, and an occurrence smaller than the
budget does not "cover" it — both are spending patterns, which the bar
already describes. And an overspent row is never told what is still coming:
"284,00 planned for 12.06" under a bar past 100 % reads as reassurance.

### `PlannedOccurrence` gained a `category_id`

Touchpoints call the planned service "read-only use", and this is the one
thing added to it: the occurrence carried `category_name` but not the id, and
matching a row to its schedule by name would break the moment two parents
have a "Subscriptions" child. One additive field, one construction site.

### Dates, not ordinals

The plan's prose writes the note as "Paid in full on the 1st" and
"284,00 zł planned for the 12th". English ordinals do not survive
translation, and building them per locale is a lot of machinery for a
12px line. Both notes use `DD.MM` instead — the same date format the
restyled ledger uses, and the natural one in Polish.

### KAL-BUD-012 needed an e2e, not a unit test

The plan tags it "@automated via unit test on the service note", but
`scripts/spec_coverage.py` only scans `tests/e2e` and `tests/integration`;
a `Covers:` in `tests/unit` counts for nothing. The pure rule still has its
unit tests (eight of them) and the wiring has two more, but the scenario is
carried by `tests/e2e/test_budget_realization.py`.

`KAL-BUD-013` is new and not in the plan: replacing the status word with a
bar is user-facing behaviour, and Working Agreement §5 wants a scenario for
it. It also pins the thing the plan is actually about.

### The status word kept its keys, and its meaning

`STATUS_LABEL_KEY` and the thresholds are untouched — the bar's colour is
`RealizationStatus` by another name (`PACE_FILL` in `budgets/constants.py`),
and the word itself is the bar's tooltip, alongside the elapsed percentage.
`STATUS_COLOUR` was deleted: it mapped statuses to Quasar badge colours, and
the badge is gone.

`col_status` became `col_pace` rather than gaining a sibling — the column is
the bar now, and a leftover key is a key someone re-adds a badge for.

### One test outside this plan had to be fixed

`tests/e2e/test_money_flow.py` asserts that the Surplus KPI is shown, which
happens when the month's income exceeds its expenses — over the *whole*
database, every other e2e test's seeded rows included. It seeded 5 000 of
income against 1 200 of its own expenses and relied on the rest of the suite
staying under that margin. The two rows this plan's e2e seeds (2 200 of
current-month expenses, needed to have anything to show a pace bar for)
pushed the suite over.

The test now seeds income large enough to actually establish its own
precondition. That is a strengthening, not a loosening: the alternative —
accepting either Surplus or Deficit — would have made KAL-FLW-002 assert
nothing.

### Not done

The `[manual]` criterion (seed data compared to artboard 2b in light and
dark) is the owner's visual pass. The Overview tab, the four summary KPIs
and the flat/by-parent toggle are untouched, as Scope says.
