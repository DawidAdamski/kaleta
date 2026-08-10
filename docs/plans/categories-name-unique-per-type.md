---
plan_id: categories-name-unique-per-type
title: Allow the same category name for income and expense (uniqueness per type)
area: categories
effort: small
status: draft
roadmap_ref: ../roadmap.md#categories
---

# Allow the same category name for income and expense

## Intent

A user cannot create a root category with the same name on both sides of
the ledger — e.g. "Nieprzypisane" (Unassigned) as an *expense* category
and again as an *income* category. The duplicate check ignores
`Category.type`, so the second create fails with "Category name … already
exists under the same parent". Income and expense trees are separate
mental namespaces; the same name must be allowed once per type.

## Root cause

- `CategoryService.create()` enforces uniqueness manually on
  `(name, parent_id)` only (SQLite treats `NULL != NULL` in unique
  constraints, hence the manual check for root categories):

  ```python
  stmt = select(Category).where(Category.name == data.name)
  if data.parent_id is None:
      stmt = stmt.where(Category.parent_id.is_(None))
  else:
      stmt = stmt.where(Category.parent_id == data.parent_id)
  if (await self.session.execute(stmt)).scalars().first():
      raise ConflictError(...)
  ```

- The DB constraint mirrors it: `uq_categories_name_parent
  (name, parent_id)` from [ADR-018](../adr/018-category-uniqueness-scoped-to-parent.md).
- Bonus finding: `CategoryService.update()` has **no duplicate check at
  all** — a rename can silently create a duplicate that `create()` would
  reject.

## Scope

- **Service — `create()`**: add `.where(Category.type == data.type)` to the
  duplicate check; error message unchanged.
- **Service — `update()`**: apply the same `(name, parent_id, type)` check
  on rename/move, excluding the category's own id. This closes the silent
  rename-duplicate hole.
- **Model + migration**: replace `uq_categories_name_parent` with
  `uq_categories_name_parent_type (name, parent_id, type)`. SQLite needs a
  table rebuild — use `op.batch_alter_table("categories")` in the new
  alembic revision (both directions).
- **Type-consistency guard (verify, add if missing)**: with type in the
  key, two same-named siblings under one parent could differ only by type.
  Check whether `create()`/`update()` enforce `child.type == parent.type`;
  if not, add that validation so the per-type uniqueness cannot produce
  mixed-type subtrees.
- **ADR**: amend ADR-018 with a superseding note (or add a new ADR):
  uniqueness is scoped to parent **and type**.
- **BDD**: add `KAL-CAT-012 @planned` to `docs/bdd.md` (Feature: Category
  Management) — creating "Nieprzypisane" as expense and again as income at
  root succeeds; duplicate within the *same* type still fails
  (KAL-CAT-010 stays valid). Retag `@automated` once the unit/e2e tests
  land.
- **Template apply / seed**: `apply_template()` skips existing entries by
  name — confirm the skip logic keys on `(name, type)` after the change so
  income/expense templates don't skip each other's entries.

Out of scope: any UI changes (the Categories page already separates
income/expense lists); merging or renaming existing user data.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_category_service.py -q`
- `grep -q "KAL-CAT-012" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- `[manual]` In the UI: create root category "Nieprzypisane" as expense,
  then again as income — both succeed; creating a second expense
  "Nieprzypisane" at root still shows the duplicate error; renaming a
  category onto an existing same-type sibling name is rejected.

## Touchpoints

- `src/kaleta/models/category.py` (`__table_args__`)
- `alembic/versions/<new>_categories_unique_name_parent_type.py`
- `src/kaleta/services/category_service.py` (`create`, `update`)
- `docs/adr/018-category-uniqueness-scoped-to-parent.md` (amend) or new ADR
- `docs/bdd.md` (KAL-CAT-012)
- `tests/unit/services/test_category_service.py`

## Open questions

1. Should the child-type guard hard-fail or auto-inherit the parent's
   type? Default: **hard-fail** with a clear ConflictError — silent
   coercion hides user mistakes.

## Implementation notes

_Filled in as work progresses._
