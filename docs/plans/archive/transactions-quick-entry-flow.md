---
plan_id: transactions-quick-entry-flow
title: Quick entry — Enter saves from any field, remembered context, save and add next
area: transactions
effort: small
status: archived
archived_at: 2026-09-25
roadmap_ref: ../../roadmap.md#transactions
---

# Quick entry — Enter saves from any field, remembered context, save and add next

Gap-closing plan for issue #2 (`KAL-QIK-001`…`003`), from
[`audit-planned-vs-code`](audit-planned-vs-code.md).

## What exists (2026-09-23)

- Alt+N opens the add dialog (and `/transactions?new=1` globally); the
  amount field takes focus; Tab order is native.
- Enter-to-save is a `ui.keyboard` handler with NiceGUI's default
  `ignore=['input','select','button','textarea']` — so **Enter does
  nothing while typing in a field** (`add_dialog.py`).
- `_reset_dialog` never resets account/date, so context survives *by
  accident* within one page load and is lost on any reload.
- No "save and add next"; every save closes the dialog.
- No test presses Alt+N or Enter.

## Scope

- **QIK-001** — Enter submits from the dialog's inputs (keydown on the
  inputs, not the global keyboard element).
- **QIK-002** — remember last account and date in user storage; reset
  amount/description/payee deliberately.
- **QIK-003** — "Save and add next" button (and shortcut): saves,
  clears amount and payee, keeps account and date, stays open.

## Acceptance criteria

- `grep -cE "KAL-QIK-00[1-3] @automated" docs/bdd.md | grep -q '^3$'`
- `uv run python scripts/spec_coverage.py`

## Open questions

- Remember date across days? Default: keep the date only for the same
  calendar day; otherwise today.

## Implementation notes

- **Open question — date across days:** took the default. The context stores
  `saved_on` next to the date; the date is preselected only when `saved_on`
  is today, otherwise the dialog opens on today
  (`QuickEntryContext.date_for`, `views/transactions/quick_entry.py`).
- **Storage:** `app.storage.user["quick_entry_context"]` =
  `{account_id, date, saved_on}`. Malformed values read as "nothing
  remembered". Account precedence on open: remembered account (if it still
  exists) → Settings default account → first account. The context is
  applied on every open (`AddDialogContext.open`), not at build time, so it
  survives reloads and the `?new=1` path.
- **QIK-001:** the page-level `ui.keyboard` Enter handler is removed. It
  ignored keys typed into inputs (so Enter did nothing while typing), and
  it fired `submit()` even with the dialog closed. Enter is now bound with
  `keydown.enter` on the amount, description, date and the two FX inputs.
  Selects are left out on purpose (Enter picks a menu option there), and so
  is the notes textarea (Enter is a newline). The e2e test picks the
  category by keyboard, then Tabs to the date and presses Enter.
- **QIK-003 shortcut:** Ctrl+Enter (Cmd+Enter on macOS) in the same inputs
  = "Save and add next". The button tooltip mentions it.
- **What "add next" clears:** amount, payee (per the scenario), plus
  description, notes, category, tags, split lines and FX fields — they
  describe one receipt. A stale category would also block the payee
  autofill, which only fills an empty category. Type, account and date
  carry over. Focus returns to the amount.
  For a transfer, the destination account carries over too: a run of
  transfers repeats the same pair of accounts, and closing the dialog still
  clears it (`_reset_dialog`).
- **Module placement:** `quick_entry.py` sits under `views/` next to
  `views/settings/user_prefs.py`. It holds per-user UI state in
  `app.storage.user`, with no DB access, so it is not service logic.
- **Reset on close:** `_reset_dialog` now clears amount and description
  deliberately (it used to leave them to the next open).
- **E2e isolation:** the suite shares one browser storage state, so the
  QIK-002 test ends by saving one more entry dated today. Without that,
  later tests would inherit the 2026-07-05 date.

## Implementation

Landed on 2026-09-25 (PR #149).

| SHA | Author | Date | Message |
|---|---|---|---|
| `4ef7c6f` | Dawid Adamski | 2026-09-25 | Merge pull request #149 from DawidAdamski/plan/transactions-quick-entry-flow |

**Files changed:**
- docs/bdd.md
- docs/plans/transactions-quick-entry-flow.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/views/layout.py
- src/kaleta/views/transactions/add_dialog.py
- src/kaleta/views/transactions/quick_entry.py
- tests/e2e/ledger.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_quick_entry.py
- tests/e2e/test_transactions.py
- tests/unit/views/test_quick_entry_context.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
