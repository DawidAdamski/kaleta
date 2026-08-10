---
adr_id: "018"
title: "Category Uniqueness Scoped to Parent and Type"
status: accepted
---

# ADR-18: Category Uniqueness Scoped to Parent and Type

- **Decision**: Category names are unique within `(name, parent_id, type)`
  (`uq_categories_name_parent_type`). The same display name may appear once
  per type under the same parent (e.g. root "Nieprzypisane" as both income
  and expense).
- **Rationale**: Income and expense trees are separate mental namespaces.
  Scoping only to `(name, parent_id)` blocked the same label on both sides of
  the ledger. Including `type` keeps siblings unique within a tree while
  allowing cross-type reuse. Child categories must still match their parent's
  type so the wider key cannot create mixed-type subtrees.
- **Consequence**: Migration
  `alembic/versions/f3c5d7e9a1b2_categories_unique_name_parent_type.py`
  replaces `uq_categories_name_parent`. Service-layer duplicate checks mirror
  the composite key (SQLite treats `NULL != NULL` for root rows).
  `CategoryService.create` / `update` hard-fail when a child's type differs
  from its parent's.

## History

- Originally accepted as `UNIQUE(name, parent_id)` only
  (`uq_categories_name_parent`, migration `e3f4a5b6c7d8`). Superseded in place
  to include `type` when same-name income/expense roots became a product
  requirement (plan `categories-name-unique-per-type`).
