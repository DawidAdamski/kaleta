---
plan_id: transactions-display-defaults
title: Settings — default ledger page size and grouping
area: views (settings, transactions)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Settings — default ledger page size and grouping

## Intent
Dogfooding request: let the user choose, in Settings, how the Transactions
list opens — how many rows per page and how they are grouped — so it is not
re-set to 50/ungrouped on every visit. Also widen the in-page page-size options
to the requested 50 / 100 / 200 / 500 (they were 25 / 50 / 100 / 200).

## Scope
- New per-user prefs `transactions_page_size` and `transactions_grouping`,
  following the existing `app.storage.user` + `user_prefs` getter + settings
  widget pattern (same as `transactions_upcoming_days`).
- The Transactions page opens on those values; its own selector/toggle still
  override for the session.
- The in-page page-size selector offers 50/100/200/500.

Not touched: the ledger query itself, grouping logic, the selector/toggle
behaviour — only their initial values and the offered sizes.

## Acceptance criteria
- `./scripts/verify.sh --e2e`
- `uv run python scripts/spec_coverage.py`

## Implementation notes
- Prefs:
  - `settings/constants.py`: `DEFAULT_TRANSACTIONS_PAGE_SIZE = 50`,
    `TRANSACTIONS_PAGE_SIZE_CHOICES = (50, 100, 200, 500)`,
    `DEFAULT_TRANSACTIONS_GROUPING = "none"`,
    `TRANSACTIONS_GROUPING_CHOICES = ("none", "week", "month")`.
  - `settings/user_prefs.py`: `get_transactions_page_size()` /
    `get_transactions_grouping()`, each validating the stored value against the
    offered choices and falling back to the default (an older build or a
    hand-edited session cannot open an unknown size/grouping).
- UI: a "Transactions list" card on the **Features** settings tab, with a
  page-size segment (50/100/200/500) and a grouping segment reusing the
  ledger's own `transactions.group_*` labels; both persist via `set_user_key`.
- Consumption: `transactions/page.py` seeds `filters["page_size"]` and
  `filters["grouping"]` from the getters (was `DEFAULT_PAGE_SIZE` / `"none"`).
- In-page selector: `components/transaction_table.py` `PAGE_SIZES` →
  `[50, 100, 200, 500]`. Kept in two places (component + settings constant)
  because the component should not import the settings layer; a unit test
  (`test_ledger_page_sizes_match_the_in_page_selector`) asserts they stay equal.
- Tests: unit tests guard the choices/default consistency; e2e
  `test_settings_ledger_defaults.py` (KAL-SET-032) sets 200 rows + month
  grouping in Settings and asserts the ledger opens with the page-size control
  on 200 and the grouping toggle on Month. Fail-on-old verified by reverting
  `features_tab.py` (the settings card, hence the "200" control, disappears).
- Shared-session caveat: the suite runs on one shared login, so
  `app.storage.user` persists across tests. The e2e sets a ledger-wide pref,
  which leaked into every other transactions test (7 failed on the first full
  run — grouping/page size not the default they assume). Fixed by restoring the
  default (50 rows / no grouping) in a `finally`, the same "left as found"
  convention `test_settings_week_debug.py` uses for the weekly-grouping knob.
