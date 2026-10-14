---
plan_id: transactions-search-render-race
title: Transactions search renders a second table (async-refresh race)
area: views (transactions)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
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
1. **Render token** (`transactions/page.py`): bump a counter at the top of
   `transaction_table()`, capture it, and after the awaited fetch return early
   if a newer render has started. Only the latest render paints — no stacked
   tables, eyebrow always matches its own footer. Covers every refresh source,
   not just typing.
2. **Debounce the search input** (`filter_bar.py`): `debounce=300` on the
   Quasar input, so a word is one search (one refresh) instead of one per
   letter — fewer queries and a much narrower overlap window.

## Scope
Just the two view files + the search box. Not touched: the service layer
(`count`/`list` already honour `search`), other filters (same refresh path, now
covered by the token), pagination.

## Acceptance criteria
- `./scripts/verify.sh --e2e`
- `uv run python scripts/spec_coverage.py`

## Implementation notes
- e2e `test_transactions_search_race.py` (KAL-TXN-020) types the search token
  **character by character with `delay=0`** — faster than a DB round-trip, so
  the per-keystroke refreshes genuinely overlap. It asserts the ledger card
  holds exactly one `.q-table` and that the eyebrow count matches the
  "Showing 1–3 of 3" footer. Fail-on-old / pass-on-new verified by swapping
  `main`'s `page.py` + `filter_bar.py` under it: on `main`, delay=0 typing
  paints **12** tables (3/3 fail); the fix leaves one (3/3 pass). `fill` emits
  a single event and never reproduces the race, which is why the existing
  `search_ledger` helper never caught it.
- The token guard sits immediately after `await with_session(_fetch)`, before
  the first DOM write (`eyebrow.set_text`), so a superseded render touches
  nothing.
