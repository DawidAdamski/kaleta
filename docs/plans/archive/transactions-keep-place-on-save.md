---
plan_id: transactions-keep-place-on-save
title: Editing a transaction keeps the reader's place
area: transactions
effort: small
status: archived
archived_at: 2026-10-15
roadmap_ref: ../../roadmap.md#transactions
---

# Editing a transaction keeps the reader's place

## Intent
Dogfooding bug #22: saving a change to an existing transaction re-reads
the ledger and snaps it back to page 1 at the very top. On a long ledger
you lose your spot every time you fix one row — tiring and disorienting.
Editing one existing row should not move you: the row's page and scroll
offset are still exactly where you want to be.

## Scope
- **Edit** (`build_edit_dialog`) and **pair-as-transfer** (`_pair_selected`)
  now refresh *in place*: the current page is kept and the scroll offset is
  restored once the table has rebuilt. With a filter active an edit (or a
  pair) can still push a row off the current page — e.g. editing the only row
  on the last page so it no longer matches a search — so the table render
  clamps `filters["page"]` to the last page that actually holds rows and
  repaints once. The common case (no overflow) keeps the exact page.
- **Add** keeps the old behaviour (`_apply_filters`, reset to page 1): a
  brand-new row belongs at the top where the reader can see it landed.
- **Delete** keeps the old behaviour too (reset to page 1): a multi-delete
  changes the row set materially and could empty the current last page, so
  returning to a known-good state is the safer default. Out of scope here.
- The edit/pair callback becomes `async` so it can read `window.scrollY`
  before the repaint; `on_saved` on the edit dialog is now
  `Callable[[], Awaitable[None]]`. Add/delete callbacks stay synchronous.

**Not in scope:** scroll restore is best-effort cosmetics and is not
asserted by the e2e (timing-dependent) — the deterministic contract is
*the page is kept (or clamped to the last non-empty page)*.

## Acceptance criteria
- `uv run pytest tests/e2e/test_transactions_keep_place.py -q` — editing a
  row on page 2 leaves the ledger on page 2 (old code bounced to page 1).
- `uv run ruff check src/kaleta/views/transactions`
- `uv run mypy src/kaleta/views/transactions/page.py src/kaleta/views/transactions/edit_dialog.py`
- `./scripts/verify.sh --e2e` green (view change → e2e mandatory, rule 8).

## Implementation notes
- The fix is a new async helper `_refresh_keeping_place` in `page.py`
  alongside `_apply_filters`. It captures `window.scrollY` (best-effort,
  2s timeout, swallows failures), repaints the three refreshables *without*
  touching `filters["page"]`, then restores the offset inside a
  `requestAnimationFrame` so the refreshed table has laid out and the
  document is tall enough for the offset to be reachable again.
- Why pair is included: `pair_selected_as_transfer` mutates two visible
  rows in place; it is a save, not a structural change, so keeping place
  matches the user's mental model ("every saved change" — #22).
- Why delete is not: a bulk delete can leave the current page past the new
  last page. Honouring the scroll there would need a re-fetch + clamp; the
  reset-to-top path is correct and already shipped. Logged as a possible
  follow-up if dogfooding flags it.

## Implementation

Landed on 2026-10-15.

| SHA | Author | Date | Message |
|---|---|---|---|
| `2d44fc4` | Dawid Adamski | 2026-10-15 | Merge pull request #265 from DawidAdamski/fix/transactions-keep-place-on-save |
| `f46abc6` | Dawid (Ani) | 2026-10-15 | fix(transactions): clamp page to last non-empty page after in-place refresh |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/transactions-keep-place-on-save.md
- src/kaleta/views/transactions/edit_dialog.py
- src/kaleta/views/transactions/page.py
- tests/e2e/test_transactions_keep_place.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `uv run pytest tests/e2e/test_transactions_keep_place.py -q` | 0 |
| `uv run ruff check src/kaleta/views/transactions` | 0 |
| `uv run mypy src/kaleta/views/transactions/page.py src/kaleta/views/transactions/edit_dialog.py` | 0 |
| `./scripts/verify.sh --e2e` | 0 |

