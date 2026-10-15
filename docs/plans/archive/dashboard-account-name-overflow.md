---
plan_id: dashboard-account-name-overflow
title: Dashboard account tiles clip long names instead of overflowing the card
area: dashboard
effort: small
status: archived
archived_at: 2026-10-15
roadmap_ref: ../../roadmap.md#dashboard
---

# Dashboard account tiles clip long names instead of overflowing the card

## Intent
Dogfooding #19: on the dashboard the balance card names its largest accounts
as quiet tiles under the hero figure. With several long names sharing the row,
each tile is narrow — and the name was rendering at its full intrinsic width,
spilling past the tile and clean off the card's right edge (seen on a real
ledger with names like "eKonto oszczędnościowe — …"). The tile's `truncate`
was present but inert.

## Root cause
`_account_chip` (`balance_card.py`) put `truncate`
(`overflow:hidden; text-overflow:ellipsis; white-space:nowrap`) on the name
label, but the label had no width bound to the tile. In a flex column the
nowrap label kept its content width (~340px) instead of the tile's (~145px),
so there was nothing to clip: the text overran the tile and the card. Measured
on the running app with three long-named accounts: label right edges at
824/949px against a card right edge of 788px.

## Scope
- **`balance_card.py` only:** bind the name label to the tile width
  (`w-full`) so `truncate` clips to an ellipsis, and add a `tooltip(name)` so
  the full name stays reachable once cut. The tile column keeps its existing
  `flex-1 min-w-32` wrap behaviour (artboard `1c`) untouched.

**Not in scope:**
- Any change to how many tiles show, their order, or the "Other accounts (N)"
  fold — only the overflow is fixed.
- Wrapping names to two lines: the card is a compact KPI, one line + tooltip
  is the lighter answer and keeps the hero figure dominant.

## Acceptance criteria
- `uv run pytest tests/e2e/test_dashboard_account_overflow.py -q`
- `./scripts/verify.sh --e2e` green (view changed → e2e mandatory, rule 8).

## Implementation notes
- Verified fail-on-old / pass-on-new by swapping in `git show main:…balance_card.py`:
  the test fails on the old widget (`label right=848.3 > card right=788.0`) and
  passes on the fix.
- The e2e asserts the true invariant — no account tile's name label reaches past
  the card's right edge — rather than a pixel width, so it holds whichever
  accounts the shared e2e instance ranks into the three tiles.
- No new i18n keys: the tooltip reuses the account name.

## Implementation

Landed on 2026-10-15.

| SHA | Author | Date | Message |
|---|---|---|---|
| `1d1c67e` | Dawid Adamski | 2026-10-15 | Merge pull request #269 from DawidAdamski/fix/dashboard-account-name-overflow |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/dashboard-account-name-overflow.md
- src/kaleta/views/dashboard_widgets/balance_card.py
- tests/e2e/test_dashboard_account_overflow.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

