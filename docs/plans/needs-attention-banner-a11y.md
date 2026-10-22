---
plan_id: needs-attention-banner-a11y
title: Desktop "Needs attention" banner items reachable by keyboard
area: dashboard
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#dashboard
---

# Desktop "Needs attention" banner items reachable by keyboard

## Intent
On the desktop dashboard the "Needs attention" banner lists each wizard
action as an inline item that navigates on click. Those items are
pointer-only: a bare `ui.row()` with `cursor-pointer` and a `click`
handler, no `role`, no `tabindex`, no key handler. A keyboard user cannot
reach or activate them, and assistive tech does not announce them as
controls. The phone rows were already fixed; the desktop banner was not.

## Scope
- Make each desktop banner item (`_render_row` in
  `src/kaleta/views/dashboard_widgets/wizard_actions.py`) a real control:
  `tabindex="0" role="button"` and `keydown.enter` / `keydown.space.prevent`
  handlers that run the same `ui.navigate.to(item.href)` the click runs.
- Keep `data-action-kind` / `data-severity` and the click behaviour
  byte-for-byte — the ranking and routing tests read that DOM.
- Not in scope: the phone functions (`_row_element`, `_render_card_row`),
  the "Open" button, any restyle, any wording.

## Acceptance criteria

- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `grep -q "KAL-DSH-012" docs/bdd.md`
- `grep -q "Covers: KAL-DSH-012" tests/e2e/test_wizard_actions_widget.py`

## Touchpoints
- `src/kaleta/views/dashboard_widgets/wizard_actions.py` — `_render_row`.
- `docs/bdd.md` — new scenario KAL-DSH-012 under Dashboard Customization.
- `tests/e2e/test_wizard_actions_widget.py` — new e2e test, added after the
  ranks test.

## Open questions
None.

## Implementation notes
- The fix mirrors `_row_element` (commit `ab2cac0`), which already gives
  the phone rows `tabindex="0" role="button"` and the same
  `("click", "keydown.enter", "keydown.space.prevent")` handler loop. The
  desktop `_render_row` uses `ui.row()` rather than `ui.element("div")`,
  but `ui.row().props('tabindex="0" role="button"')` plus the same `.on`
  loop produces the identical control; the element is not restructured,
  only the attributes and key handlers are added, and the click lambda is
  unchanged so the routing/ranking DOM is byte-for-byte the same.
- No `aria-label`: the row's own text is its accessible name, the same
  rationale `_row_element`'s docstring gives — a copy in an attribute is a
  second string to keep in step with the first.
- No new user-facing strings, so no new i18n keys.
- The phone version (`ab2cac0`) shipped **without its own BDD scenario**,
  so this slice adds KAL-DSH-012 to cover the keyboard-activation pattern
  that both renderings now share, verified on the desktop banner (the one
  that was broken).
- The e2e test lives inside `test_wizard_actions_widget.py`, defined after
  `test_widget_ranks_items_and_links_rows`, and asserts on a danger-severity
  overdue loan rather than an info renewal. The e2e app is session-scoped
  and the banner caps at `MAX_ROWS=12`; a second renewal-due subscription
  would have displaced the ranks test's info-tail subscription into the
  "+N more" overflow and failed it. A danger item always ranks top-visible,
  and same-file definition order guarantees this seed is added only after
  the fragile sibling has already run. The latent fragility it exposed is
  logged in `docs/plans/chores.md`.
