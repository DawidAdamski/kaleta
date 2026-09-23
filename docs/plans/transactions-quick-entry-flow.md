---
plan_id: transactions-quick-entry-flow
title: Quick entry — Enter saves from any field, remembered context, save and add next
area: transactions
effort: small
status: draft
roadmap_ref: ../roadmap.md#transactions
---

# Quick entry — Enter saves from any field, remembered context, save and add next

Gap-closing plan for issue #2 (`KAL-QIK-001`…`003`), from
[`audit-planned-vs-code`](archive/audit-planned-vs-code.md).

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
