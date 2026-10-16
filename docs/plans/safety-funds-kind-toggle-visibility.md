---
plan_id: safety-funds-kind-toggle-visibility
title: Safety funds — switching fund type back to Emergency restores its fields
area: views (safety_funds)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Safety funds — switching fund type back to Emergency restores its fields

## Intent
Dogfooding #20 (chores.md). In the "New reserve fund" dialog the Emergency
fund type shows two extra controls — "Cover [N] months of expenses" and the
"Derive target from my spending" switch. Switching the Fund type to another
kind (Irregular / Vacation) correctly hides them, but switching **back** to
Emergency does **not** bring them back: the dialog stays in the reduced layout
with no way to reach the months-to-cover input again (the user reproduced this
with screenshots: Emergency → Irregular → Emergency leaves the fields gone).

## Root cause
`_on_kind_change` keys its logic off the raw Quasar event payload `e.args`:

```python
is_emergency = e.args == ReserveFundKind.EMERGENCY.value
multiplier_row.set_visibility(is_emergency)
...
name_in.set_value(defaults[e.args])
```

For a `ui.select` the `update:model-value` payload is **not** the option key
string, so `e.args == "emergency"` is always False — the emergency-only rows
never re-show, and `defaults[e.args]` can't resolve the key either. The first
open looks correct only because `_open_add_dialog` / `_open_edit_dialog` set
the visibility explicitly; the regression appears the moment the dropdown is
used. Fix: read the component's own `kind_in.value` (the selected option key),
not `e.args`.

## Scope
- **`src/kaleta/views/safety_funds.py`:** `_on_kind_change` reads `kind_in.value`
  instead of `e.args` for the emergency check, the GOAL/target-date check, and
  the default-name lookup. No other behaviour changes.

**Not in scope:**
- The Goals filter, the derived-target maths, or any field other than the
  kind-driven show/hide.

## Touchpoints
- `src/kaleta/views/safety_funds.py`
- `tests/e2e/test_reserve_funds.py`
- `docs/bdd.md`

## Acceptance criteria
- `uv run pytest tests/e2e/test_reserve_funds.py -q` green.
- Fail-on-old: the new KAL-FND-004 test fails on the current `e.args` code
  (the Cover/Derive rows stay hidden after Emergency → Irregular → Emergency)
  and passes on the fix.
- `./scripts/verify.sh --e2e` green (view changed → e2e mandatory, rule 8).

## Implementation notes
- One-line cause confirmed by TDD: `_on_kind_change` compared `e.args` (the raw
  Quasar `update:model-value` payload, not the option key) against the kind
  value, so it was never `True` for Emergency after a dropdown change. Reading
  `kind_in.value` fixes the show/hide and the `defaults[...]` name lookup.
- KAL-FND-004 reproduced the user's screenshots exactly: on the old code, after
  Emergency → Irregular → Emergency, the dialog kept only Fund type / Name /
  Target / Backing (no "Cover … months", no Derive switch); the test's final
  `expect(cover).to_be_visible()` failed. On the fix it passes.
- The test opens the Add dialog and never saves; it seeds one backing account
  (the dialog refuses to open without one) and deletes it in `finally`.
- No i18n keys added; no new user-facing strings.
