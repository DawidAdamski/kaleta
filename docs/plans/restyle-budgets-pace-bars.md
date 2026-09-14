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
  payment" and `KAL-BUD-013` "a pace bar replaces the status word",
  both @automated by e2e (see Implementation notes).

Out of scope: threshold values (`REALIZATION_WARNING_THRESHOLD_PCT`
unchanged); the Overview tab chart; budget editing.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_budget_service.py -q`
- `uv run pytest tests/e2e/test_budget_realization.py -q`
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
  `tests/e2e/test_budget_realization.py` (new)

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

### The note has four clauses, and each one is a way it could lie

"Paid in full" is three equalities and a date, and each one is a way the
line could otherwise be false:

- the occurrence is **due** (`bill.date <= today`) — a 2 000 bill dated the
  25th has not been paid on the 10th, whatever else was spent;
- the bill **is** the budget (`bill.amount == planned`) — 2 000 charged to a
  1 900 budget is an overspend of 100, and 2 000 spent against a 2 100 bill
  is a bill still partly outstanding;
- the budget is used up **exactly** (`actual == planned`) — an equality, not
  a range: one coffee charged to the rent category and the row really is
  over, and "as expected" under a red bar is reassurance for the one row
  that should never get any.

Each has its own unit test. The branch is still a **heuristic** in one
respect: it does not require the occurrence to have been *posted*, only to
exist and be due. A 2 000 plan that was never booked, plus 2 000 of
unrelated spending in the same category, gets the note. Requiring the post
would be stricter and wrong far more often — recording rent by hand instead
of posting the plan is the common path, and it is the one the e2e drives.

**Posted occurrences count for one branch and not the other.** The schedule
is fetched whole and each entry is marked posted or not
(`ScheduledExpense`). "Paid in full" reads the whole of it: posting the rent
plan is *how* the actual got there, so excluding posted occurrences would
erase the explanation exactly when the row starts needing it. "Planned on"
reads only the unposted ones: an occurrence that has been booked is already
in the actuals, and announcing it as still to come would count the same
money twice under a bar that already includes it. Neither half needs the
amount-and-date matching open question 1 rules out — the planned service
keeps that bookkeeping itself.

A bill **due today and unpaid** counts as upcoming, not past — the one day
the "planned for 12.09" line matters most. The paid case is taken by the
branch above it, so the two cannot both fire.

The field is called `note` rather than the plan's `explanation`, which reads
better through `note_text` and the two i18n keys.

### A deactivated plan loses its note

`_expense_schedule` reads `get_occurrences` with the default
`active_only=True`. A plan that was posted this month and then switched off
— the month you move out, say — takes its "Paid in full" line with it, even
though the money did go out against it. Passing `active_only=False` would
fix that half and break the other: the "planned on" branch would start
announcing money from plans the user deliberately turned off. The right fix
is per-branch, which means two schedule reads for an edge case; left as is.

### The schedule is read twice, on purpose

`_expense_schedule` calls `get_occurrences` once in full and once with
`exclude_posted=True`, and diffs them to mark each entry. One pass would be
cheaper, but the posted flag is the planned service's own bookkeeping and
there is no public way to ask for it inline. Both calls happen only for the
month actually on screen, and only when it is the current one.

### The note only knows the category it is filed under

The schedule is keyed on the occurrence's own `category_id`, so a plan filed
under a child category does not explain a budget set on its parent, or the
reverse. That is the same granularity the realization rows themselves use
(one row per category, parent shown as a label), so the note is no narrower
than the thing it annotates — but it does mean a household that budgets at
parent level and plans at child level gets no notes. Left as is; changing it
means deciding whether a parent's budget is the sum of its children's, which
is `budgets-plan-unification` territory.

### A bar the schedule explains still keeps its colour

A rent row paid on the 1st is at 100 % used against a 5 % elapsed month, so
`CategoryRealization.status` calls it WARNING and the bar is amber — the
note explains it, but does not repaint it. That is deliberate: the
thresholds are out of scope (Scope says so), and amber is not *wrong* — the
money did go out ahead of the month. What the row must not do is read as an
**overspend**, and it does not: the fill is never `--k-expense` while the
note stands, which is what KAL-BUD-012 asserts and how its step is worded.

### `PlannedOccurrence` gained a `category_id`

Touchpoints call the planned service "read-only use", and this is the one
thing added to it: the occurrence carried `category_name` but not the id, and
matching a row to its schedule by name would break the moment two parents
have a "Subscriptions" child. One additive field, one construction site.

### Amounts keep the page's format, without a currency

The plan writes the note as "284,00 zł planned for the 12th". The figure
uses `,.2f` like every other cell in the row, and carries no `zł`: the row's
Planned, Actual and Remaining columns do not, the account currency is
configurable, and a hard-coded suffix under a column of bare numbers would
be the only place on the page claiming to know it.

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
unit tests (fifteen of them) and the wiring has three more, but the scenario is
carried by `tests/e2e/test_budget_realization.py`.

`KAL-BUD-013` and `KAL-BUD-014` are new and not in the plan. Replacing the
status word with a bar and putting a "284,00 planned for 12.09" line under
it are both user-facing behaviour, and Working Agreement §5 wants a scenario
for each. KAL-BUD-014 seeds its bill as due **today**, which is a date every
month has — "later this month" does not exist on the 31st, and a test that
only runs for 30 days out of 31 is a test that fails on the 31st.

### The status word kept its keys, and its meaning

`STATUS_LABEL_KEY` and the thresholds are untouched — the bar's colour is
`RealizationStatus` by another name (`PACE_FILL` in `budgets/constants.py`),
and the word itself is the bar's tooltip, alongside the elapsed percentage.
`STATUS_COLOUR` was deleted: it mapped statuses to Quasar badge colours, and
the badge is gone.

`col_status` became `col_pace` rather than gaining a sibling — the column is
the bar now, and a leftover key is a key someone re-adds a badge for.

### The note wraps, and the row aligns to the top

The pace column was `w-40` (160px) and the note was `truncate`, which cut
"Opłacone w całości 01.09 — zgodnie z planem" in half — and an e2e
`to_contain_text` passes on text hidden by CSS, so no test would have caught
it. The column is `w-56` and the line wraps. The row aligns `items-start` so
a two-line note does not shove the figures down, with the bar dropped
`pt-1.5` onto the text's own line.

Row hover moved from the hard-coded `hover:bg-slate-50` to a `ROW_HOVER`
token class. The old name was already remapped to `--k-row-hover` in
`theme.py`, dark mode included, so this is not a fix — it is the rest of the
row's move to tokens finishing the job.

### The e2e must not depend on today's date

`test_a_pace_bar_replaces_the_status_word` first seeded 200 against a budget
of 800 and asserted the tooltip said "On track". `status` is WARNING when
`used_pct > elapsed_pct + 5`, and `elapsed_pct` is the day of the month — so
25 % used would have been a WARNING on the 1st through the 6th, and
`verify.sh --e2e` would have gone red on those days for no reason at all. It
seeds 5 % of the budget now, which is on track on every day of every month.

The scenario's "full bar while the month is barely elapsed" cannot be set up
from an e2e that runs on whatever today is. That half is pinned by
`test_a_posted_rent_still_carries_its_note`, which controls `today` and
asserts the row is WARNING and not OVER.

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
