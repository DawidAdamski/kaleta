---
plan_id: restyle-budgets-pace-bars
title: Restyle — Budgets/Realization pace bars with month-elapsed tick (artboard 2b)
area: budgets
effort: small
status: draft
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

_Filled in as work progresses._
