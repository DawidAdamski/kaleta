---
plan_id: categories-templates
title: Category tree templates
area: categories
effort: small
status: draft
roadmap_ref: ../roadmap.md#categories
---

# Category tree templates

## Intent

New users should not have to design a category tree from scratch. Ship
a handful of templates they can load in one click.

## Scope

- Ship 3–5 templates as JSON in the repo (e.g.
  `src/kaleta/data/category_templates/*.json`).
- Expose a "Load template" action on the Categories page.
- Loading a template appends to the existing tree — never replaces or
  deletes. Duplicate names are merged; the existing tree wins.

Proposed templates (confirm):
- `polish-household` — typical 2-adult household in Poland.
- `single-person` — minimal set focused on rent, food, transit.
- `freelancer` — business + personal split.
- `student` — rent, food, learning, leisure.

Each template: 2 top-level (Income + Expense) with ~6–12 leaves.

Out of scope:
- User-defined templates that can be saved and reloaded.
- A template marketplace.

## Acceptance criteria

- "Load template" menu appears on Categories, listing all shipped
  templates with a short description.
- Loading inserts new categories without duplicating existing ones
  (by name, case-insensitive, within the same parent).
- Confirmation dialog before import lists what will be added.
- i18n: template descriptions and category names localised.

## Touchpoints

- `src/kaleta/data/category_templates/*.json` — new files.
- `src/kaleta/services/category_service.py` — `import_template`
  method with merge-by-name semantics.
- `src/kaleta/views/categories.py` — new menu action + confirmation.
- `src/kaleta/i18n/locales/*` — template names / descriptions and
  category labels.

## Open questions

- Store category names in the JSON in English with i18n lookup, or
  store a translated object per template? Lean on i18n lookup
  (single source of truth) with a `key` field on each node.
- Should importing work across languages — i.e. a Polish install
  gets Polish labels regardless of which template was chosen?

## Implementation notes

_(filled as work progresses)_
