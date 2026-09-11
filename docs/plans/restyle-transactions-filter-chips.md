---
plan_id: restyle-transactions-filter-chips
title: Restyle — Transactions filter chips, selection total, week-group net (artboard 2a)
area: transactions
effort: medium
status: draft
roadmap_ref: ../roadmap.md#transactions
---

# Restyle — Transactions filter chips, selection total, week-group net

## Intent

The seven filters in `components/filter_bar.py` render as full Quasar
selects with floating labels and take three rows of toolbar before the
first transaction is visible. Artboard `2a` in
`docs/design/restyle/Kaleta Dashboard.dc.html` collapses them into one
row of chips that **show their value** (`01.06.2026 → 03.07.2026`,
`PKO Konto Główne +2`, `Expense`) and only show the field name when
unset (dashed `+ Category`, `+ Tag`). The table itself keeps its columns
but reads as a ledger: `DD.MM` dates in mono muted, amount as the only
right-aligned column, category as a pill, week separators carrying the
group's net. Handoff calls this (with `2b`) the highest ratio of
perceived quality to effort.

Depends on `restyle-theme-tokens` (uses `.k-filter-chip`, `.k-amount`,
`.k-mono`).

## Scope

- **Filter chips** — replace the select/input row in `render_filter_bar`
  with a chip row. Each chip is a `k-filter-chip` that opens the existing
  control (date range picker, multi-select, type select, search input,
  tag select) in a `ui.menu` / popover anchored to the chip. Chip label
  logic in a pure helper (`filter_chip_label(filters, accounts, …)`):
  date → `DD.MM.YYYY → DD.MM.YYYY`; accounts → first name `+N`; type →
  label; category / tag / search likewise. Unset chips render
  `k-filter-chip--empty` with `+ <field>`. `Clear all N` on the right,
  using `active_filter_count`. `FilterBarWidgets` keeps the same public
  handles so `page.py`'s clear path is unchanged.
- **Selection bar** — when ≥1 row is selected, the existing
  `k-selection-bar` turns warm (`#EFE3D6` light / sunken surface dark)
  and shows **selected total** on the right (sum of visible selected
  rows' signed amounts; computed in the view from the rows already
  loaded — no service call). Bulk actions unchanged.
- **Table presentation** in `transaction_table.py` (`transaction_columns`
  + `_body_slot`): date cell `DD.MM` in `k-mono` muted; amount column
  right-aligned (`align: right`), the only one; category as a pill
  (sunken surface, 999px); type column text-only; split rows show
  `call_split` icon + `Split (N)` in place of category (labels from
  `attach_split_labels` already exist); rows with notes show a
  `sticky_note_2` glyph before the description; row hover `#FAF4E9`.
- **Group separators** — the week/month separator rows (from the
  grouping toggle) carry the group's net on the right (`k-amount`, signed).
  Needs a per-group net: extend the grouping helper that builds separator
  rows to sum signed amounts of the page's rows in that group (page-scoped
  is acceptable — document it as such in the tooltip/i18n string).
- **Pagination bar** — grouping toggle moves inline into
  `render_pagination_bar` left side (it is already there — restyle only:
  toggle as segmented `k-filter-chip`s).
- i18n: new keys `transactions.filter_chip_*`, `transactions.clear_all_n`,
  `transactions.selected_total`, `transactions.group_net` in `en.json` +
  `pl.json`.
- BDD: add `KAL-PAG-005` (group separator shows net) and `KAL-TXN-014`
  (selection bar shows total) under the existing features; e2e in
  `tests/e2e/test_transactions.py`.

Out of scope: any change to filter semantics, sort, pagination or bulk
actions; the add/edit dialogs; mobile layout of the chip row (it may
wrap).

## Acceptance criteria

- `uv run pytest tests/unit/views -q`
- `uv run pytest tests/e2e/test_transactions.py -q`
- `grep -q "k-filter-chip" src/kaleta/views/components/filter_bar.py`
- `grep -q "KAL-PAG-005" docs/bdd.md`
- `grep -q "KAL-TXN-014" docs/bdd.md`
- `grep -q "selected_total" src/kaleta/i18n/locales/pl.json`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh --e2e`
- `[manual]` On seed data with date + 3 accounts + Expense set: toolbar is
  one row, chips read `01.06.2026 → 03.07.2026`, `PKO Konto Główne +2`,
  `Expense`, then dashed `+ Category`, `+ Tag`; `Clear all 3` on the
  right. Compare to artboard `2a` in light and dark.
- `[manual]` Select 3 rows: warm bar appears with the signed total;
  week grouping on: each separator shows the week net.

## Touchpoints

- `src/kaleta/views/components/filter_bar.py` (chips, popovers, label
  helper)
- `src/kaleta/views/components/transaction_table.py` (columns, body slot,
  separator rows, pagination bar)
- `src/kaleta/views/transactions/page.py` (selection bar + total)
- `src/kaleta/views/transactions/table_actions.py` (if the selection bar
  lives there)
- `src/kaleta/i18n/locales/en.json`, `pl.json`
- `docs/bdd.md`, `tests/e2e/test_transactions.py`,
  `tests/unit/views/` (new `test_filter_chip_labels.py`)

## Open questions

1. Chip popover control: reuse the existing Quasar selects inside a
   `ui.menu`, or custom lists? Default: **reuse existing selects inside a
   menu** — zero behaviour change, chips are a presentation layer.
2. Group net scope: page-only or whole result set? Default: **page-only**
   (no extra query), tooltip says "on this page".
3. Is `filter_bar.py` shared by other pages (accounts, payees)? If yes,
   keep a `variant="chips"|"classic"` flag defaulting to chips and verify
   those pages in e2e. Default: **flag**, remove classic later.

## Implementation notes

_Filled in as work progresses._
