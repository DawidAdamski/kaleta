---
plan_id: transactions-search-render-race
title: Transactions search renders a second table (async-refresh race)
area: views (transactions)
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# Transactions search renders a second table (async-refresh race)

## Intent
Dogfooding: searching the ledger paints a **second table** under the first,
and the header eyebrow count stops matching the "Showing … of N" footer below
it (screenshot: eyebrow "62 movements", footer "of 644", two stacked tables).
Only visible under real network latency — it did not reproduce in fast local
runs, which is why it went unnoticed.

## Root cause
The search box fires `update:model-value` on **every keystroke**
(`filter_bar.py`), with no debounce. Each one runs `_apply_filters()` →
`transaction_table.refresh()`. `transaction_table` is an **async** refreshable:
its body awaits the database (`count` + `list`). So typing a word puts several
refreshes in flight at once, and because each awaits, their renders interleave
— the slower one appends its table after the faster one has already painted,
leaving two tables, and `eyebrow.set_text` runs once per render so the eyebrow
ends up from a different render than the rows shown. Under latency the overlap
window is wide; locally the queries return before the next keystroke, so it
hid.

## Fix
**Render token** (`transactions/page.py`): bump a counter at the top of
`transaction_table()`, capture it, and after the awaited fetch return early if a
newer render has started. Only the latest render paints — no stacked tables, and
the eyebrow always matches its own footer. This covers every refresh source
(search, grouping, page size, filters, pagination), not just typing, which is
why it is the whole fix.

A `debounce=300` on the search input was tried alongside it. It was dropped: it
coalesces keystrokes into one refresh, which *masks* the race on the search path
rather than fixing it, and that mask also hid the token from its own test (the
e2e then passed through the debounce without ever exercising the guard). The
token alone is correct for every path. Cutting per-keystroke queries is a real
but separate efficiency win — a perf chore, not part of this correctness fix.

## Scope
One view file (`transactions/page.py`). Not touched: the service layer
(`count`/`list` already honour `search`), the filter bar, other filters (same
refresh path, now covered by the token), pagination. Plus the e2e test, the
BDD scenario, and this plan.

## Acceptance criteria
- `./scripts/verify.sh --e2e`
- `uv run python scripts/spec_coverage.py`

## Implementation notes
- e2e `test_transactions_search_race.py` (KAL-TXN-020) types the search token
  **character by character with `delay=0`** — faster than a DB round-trip, so
  the per-keystroke refreshes genuinely overlap. It asserts the ledger card
  holds exactly one `.q-table` and that the eyebrow count matches the
  "Showing 1–3 of 3" footer. With no debounce in the way, this test exercises
  the token directly: reverting only the token (`main`'s `page.py`) makes it
  paint **12** tables (3/3 fail); the fix leaves one (3/3 pass). `fill` emits a
  single event and never reproduces the race, which is why the existing
  `search_ledger` helper never caught it.
- The token guard sits immediately after `await with_session(_fetch)`, before
  the first DOM write (`eyebrow.set_text`) and before any `ui.*` element is
  created in the body, so a superseded render touches neither the DOM nor the
  shared `page_rows` / `table_holder` state.
- Why not debounce the search box too: a 300 ms debounce coalesces the
  keystrokes into one refresh, so it hides the race on the search path instead
  of fixing it — and in doing so it hid the token from the e2e (the test passed
  through the debounce without ever reaching the guard). Reproducing the race
  from a non-debounced control (grouping toggle, filter clicks) was not
  reliable in e2e: NiceGUI coalesces the synchronous `refresh()` calls a burst
  of clicks makes into one re-run, and only genuinely separate input events
  (keystrokes) overlap. So the honest, directly-tested fix is the token alone;
  a search debounce can be revisited as a query-load chore.

## Implementation

Landed on 2026-10-21.

| SHA | Author | Date | Message |
|---|---|---|---|
| `ca9e23a` | Dawid (Ani) | 2026-10-14 | fix(transactions): stop the ledger search painting a second table |
| `63e02b3` | Dawid (Ani) | 2026-10-14 | fix(transactions): drop debounce, keep the render-token guard as the fix |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/README.md
- docs/plans/transactions-search-render-race.md
- src/kaleta/views/components/filter_bar.py
- src/kaleta/views/transactions/page.py
- tests/e2e/test_transactions_search_race.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `./scripts/verify.sh --e2e` | skipped (--fast; green at implementation time) |
| `uv run python scripts/spec_coverage.py` | 0 |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
