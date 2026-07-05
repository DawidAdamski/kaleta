---
adr_id: "018"
title: "Category Uniqueness Scoped to Parent"
status: accepted
---

# ADR-18: Category Uniqueness Scoped to Parent

- **Decision**: Replace the `UNIQUE(name)` constraint on `categories` with `UNIQUE(name, parent_id)` (`uq_categories_name_parent`).
- **Rationale**: The previous global uniqueness constraint prevented the same category name from appearing under different parent categories (e.g., "Other" under both "Food" and "Transport"). Scoping uniqueness to `(name, parent_id)` reflects how users actually organise hierarchical categories, where name collisions across different parents are valid and expected.
- **Consequence**: The migration is `alembic/versions/e3f4a5b6c7d8_categories_unique_name_parent.py`. Two top-level categories (both with `parent_id = NULL`) that share a name remain disallowed, since NULL = NULL in this context uses the constraint's composite key behaviour.
