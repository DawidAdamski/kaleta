---
plan_id: rules-category-picker-hierarchy
title: Rules — category picker shows the tree, not a flat name list
area: views (rules)
effort: small
status: in-progress
roadmap_ref: ../roadmap.md
---

# Rules — category picker shows the tree, not a flat name list

## Intent
Dogfooding #23 (chores.md): when writing an auto-categorisation rule, the
category picker is hard to use — a child category shows as its bare name with
no indication of the root it sits under, so roots and leaves look identical and
"the category is hard to find (roots missing / only subcategories shown)".

Root cause: `rules.py` builds the select options ad hoc as
`{c.id: c.name for c in cats}` — a flat list of bare names. The app already has
a shared hierarchical label builder, `CategoryService.build_option_labels()`,
which renders roots on their own and children as `Root → Child`, in tree order.
The **Reports** config zone already uses it. Rules just never adopted it.

## Decision
Replace the Rules view's ad-hoc option map with
`CategoryService.build_option_labels(await CategoryService(session).list())`,
exactly as Reports does. No new label format, no new service method — reuse
(Working Agreement rule 10). Every category (root and child, every type) stays
selectable, which matches today's behaviour; only the *labels* change.

## Scope
- **`src/kaleta/views/rules.py`:** `_load_category_options` returns
  `CategoryService.build_option_labels(cats)` instead of `{c.id: c.name}`.
- **`tests/e2e/test_rules.py`:** new test — seed a root + child expense
  category, open the Add-rule dialog, open the category select, assert the
  child renders as `Root → Child` and the root renders on its own. Clean both
  categories up in `finally` (shared worker DB — a stray category would leak
  into other tests' pickers; the #19 lesson).
- **`tests/e2e/seed_helpers.py`:** add `delete_category(category_id)` (mirrors
  `delete_account`) so the test can clean up.
- **`docs/bdd.md`:** new scenario `KAL-RUL-005` (`@automated`).

**Not in scope:**
- Which categories are *assignable* to a rule (unchanged — all of them).
- The Reports / transactions pickers (already hierarchical).
- Indented/grouped Quasar option slots — the `Root → Child` text label is the
  established app-wide convention; do not invent a second one.

## Acceptance criteria
- `uv run pytest tests/e2e/test_rules.py -q` green.
- Fail-on-old proof: with `rules.py` swapped to `git show main:…`, the new test
  FAILS (child shows as bare name, no `→`); on the fix it PASSES.
- `./scripts/verify.sh --e2e` green (view changed → e2e mandatory, rule 8).

## Implementation notes
- Reused `CategoryService.build_option_labels` verbatim — no new service code.
  Confirmed Reports (`views/reports/page.py`) already consumes it, so the label
  convention ("Root → Child", U+2192) is app-wide, not a one-off.
- Added `delete_category` to `tests/e2e/seed_helpers.py` (mirrors
  `delete_account`); the new test removes the child then the root in `finally`.
- Fail-on-old verified by swapping `rules.py` to `git show main:…`: the option
  list then renders the child as a bare "Fuel RUL005" next to "Transport
  RUL005" — two indistinguishable flat entries, exactly the dogfooding
  complaint — and the test fails; on the fix it reads "Transport RUL005 → Fuel
  RUL005" and passes.
- No i18n keys touched (labels are category names + an arrow glyph, not
  translated strings).
- The existing `test_create_categorisation_rule` (KAL-RUL-001) regressed under
  the *full* suite only: reordering the options (now by root, children
  interleaved) pushed "Groceries" out of the virtualised menu's initial DOM, so
  its no-scroll `get_by_text(...).click()` timed out. Passed in isolation
  (short list), failed under `verify --e2e` (long accumulated list). Fixed by
  routing both pickers through one `_scroll_menu_to` helper (the scroll loop
  that already lived inlined in `_select_option`); the exact-label assertion is
  unchanged — not a loosened check.
- KAL-RUL-001 also stopped using the shared "Groceries" (a template *child*,
  `children_en`, so the hierarchy now labels it "Parent → Groceries" and an
  exact "Groceries" click is flaky). It seeds a uniquely-named ROOT and deletes
  it in `finally`; the rule's `category_id` FK is `ON DELETE CASCADE`, so the
  rule goes with it — which also stops the old test leaking a permanent rule +
  category into later e2e tests. After this, `verify --e2e` is green (261
  e2e, 0 failures); an earlier run's transactions cluster was timing flakiness,
  not a deterministic regression (identical serial order passed on re-run).
