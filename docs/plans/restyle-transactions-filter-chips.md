---
plan_id: restyle-transactions-filter-chips
title: Restyle — Transactions filter chips, selection total, week-group net (artboard 2a)
area: transactions
effort: medium
status: in-progress
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
- `grep -q "FILTER_CHIP" src/kaleta/views/components/filter_bar.py`
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

### Read this before reviewing the diff

Stacked on `plan/restyle-theme-tokens`, which is not merged yet — this plan
"Depends on `restyle-theme-tokens`" for `.k-filter-chip`, `.k-amount` and
`.k-mono`. So the merge-base diff shows that plan's work too. This plan's
own diff is:

    git diff plan/restyle-theme-tokens...HEAD

and its PR is opened with `--base plan/restyle-theme-tokens`.

### Open questions — decisions taken

1. **Chip popovers reuse the existing controls.** Each chip opens a
   `ui.menu` holding the same `ui.select` / `ui.input` as before, with the
   same `on_change` handlers, so no filter semantics moved. `FilterBarWidgets`
   still hands the page the same seven widgets, which is why `_clear_filters`
   in `page.py` is unchanged.
2. **Group net is page-scoped.** `attach_group_nets` sums the rows it was
   given — the page the user is looking at — and the separator's tooltip says
   so ("Net on this page"). Summing the whole result set would mean a second
   aggregate query for a figure that sits inside one screen of scroll.
3. **No `variant="chips"|"classic"` flag.** The open question made it
   conditional on `filter_bar.py` being shared; it is not. `render_filter_bar`
   has exactly one caller (`transactions/page.py`), so a flag would have been
   a switch with one position.

### One amended criterion

`grep -q "k-filter-chip" filter_bar.py` became `grep -q "FILTER_CHIP"`. The
class name is a theme token, so the chip row asks `theme.FILTER_CHIP` for it
rather than repeating the string — which is what every other view does with
`SECTION_CARD` and friends, and what keeps a rename to one file. The
criterion's intent, "the chips shipped in `filter_bar.py`", is unchanged;
only the spelling it greps for is.

### Keyboard

Moving a `ui.select` behind a chip moves it behind a `div`, and a div takes
no focus and answers no Enter. Every filter would have become mouse-only.
Each opener therefore carries `tabindex`, `role="button"` and
`aria-haspopup`, with Enter and Space wired to `menu.open`; each `×` carries
`tabindex`, `role` and an `aria-label`; and "Clear all N" is a `ui.button`
rather than a label with a click handler.

### Clearing a chip costs one query

`ui.select.set_value([])` fires the select's own `on_change`, which *is* the
page's filter handler — so the first draft's "set it, then call the handler"
ran the filter twice per `×`. The selects now rely on `set_value` alone. The
date chip holds two fields, so `render_filter_bar` takes an optional
`on_clear_dates` and the page clears both ends in one apply instead of one
per end.

### Transfers are not a net

`net_of_rows` skips transfer rows. Both legs of an internal transfer are
booked, so summing the column as-is would show 3 000 leaving on a week when
1 500 moved between the user's own accounts and nothing left at all. The
*column* still shows each leg signed — a row says where money went, a net
says how much there is. The selection bar reads the same function, so the
two figures cannot disagree.

### The grouping toggle stayed a toggle

Scope asked for "segmented `k-filter-chip`s". A Quasar `ui.toggle` already
*is* a segmented control with the selection behaviour and keyboard handling
written; rebuilding it out of chips would have been three buttons and a
state variable to get wrong. It is styled as one pill (`.k-group-toggle`)
instead, which is what the artboard shows.

### The chips repaint, they do not rebuild

A chip's label follows the filter, so it has to change when the filter does.
Rebuilding the row through `@ui.refreshable` was the obvious way and the
wrong one: the controls live *inside* the chips, so a refresh mid-selection
would destroy the open multi-select the user was still picking from. Instead
each chip keeps handles to its own labels and icons, and
`FilterBarWidgets.refresh_chips(filters)` sets text and toggles the dashed
empty state in place. The page already called `_update_badge()` on every
filter change, so that is where the repaint hangs.

Clearing one chip is its `×`, which is a sibling of the element the menu
hangs from — not a child. A close icon inside the opener would have opened
the menu on its way to clearing the filter.

### Signs

`TransactionService.signed_amount` is new and `format_signed_amount` now goes
through it. Three things need the same sign convention — the amount column,
a group's net, and the selection total — and the only way they cannot
disagree is to have one function decide. Rows carry `amount_value` (a float
beside the formatted string) so a total never has to parse a display string
back into a number.

`date_short` joins `date` on the row for the same reason: the ledger shows
`DD.MM` but the column still sorts on the ISO value, and the full date is a
tooltip away.

### E2e: the search field moved behind a chip

Six places across four e2e files typed into `Search description` directly.
That field is now inside a menu that has to be opened first and closed again
before the rows underneath are clickable, so they all go through
`tests/e2e/ledger.py::search_ledger`. The helper is the only place that knows
where the control lives, which is the point.

### Not done

`docs/design/screenshot.png` still shows the pre-restyle ledger, and the two
`[manual]` criteria (the 2a comparison in light and dark, and the selection
bar with week grouping on) are the owner's visual pass.
