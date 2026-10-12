---
plan_id: category-templates
title: Category templates for who you are — single, family, company, car, home — combined
area: setup / categories
effort: large
status: draft
roadmap_ref: ../roadmap.md
---

# Category templates for who you are — single, family, company, car, home — combined

## Intent

A new user should not build a category tree by hand. They pick what describes their life —
*single*, *family with children*, *one company* or *two companies*, *a car* or *two cars*,
*own house*, *renting*, *pets*, … — and Kaleta builds the matching expense and income
categories (and their budgets' starting shape) from those templates, merged into one tree.
Templates can be added later the same way: buying a second car adds the second car's
categories without touching anything else.

## Scope

- **Template catalogue** (data, not code paths): each template is a set of categories
  (parent → children, type, an optional default monthly budget hint) and tags. First set:
  Single, Family (children), Company (JDG: ZUS, VAT, księgowość, …), Car, Own home (podatek
  od nieruchomości, ubezpieczenie, remonty), Rental (czynsz najmu), Pets, Student. Polish
  and English names.
- **Combining**: applying several templates merges by normalised name (the blind index
  the categories already have), so "Ubezpieczenia" appears once with every template's
  children under it. Applying a template twice adds nothing.
- **Multiples** ("2 companies", "2 cars"): a template marked *repeatable* takes a name per
  copy — "Samochód: Skoda", "Samochód: Toyota" — and creates one subtree per copy.
- **Where**: the first-run setup offers the templates as checkboxes (a family of one picks
  Single by default); Settings → Categories offers "Add from a template" later.
- **Preview before applying**: the list of categories that will be added (and the ones that
  already exist), the way the budget builder shows its diff.
- BDD: `KAL-CTP-*` for picking, combining, repeating and adding later.

## Not in scope

- Removing a template's categories (they hold transactions; deleting categories stays a
  manual act).
- Templates for other areas (accounts, reserve funds) — a later plan may reuse the format.

## Acceptance criteria

- `uv run pytest tests/integration/test_category_templates.py -q`
- `uv run pytest tests/e2e/test_category_templates.py -q`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## Touchpoints

`src/kaleta/seeders/catalog.py` (or a new `src/kaleta/templates/categories/*.toml`),
`src/kaleta/services/category_template_service.py` (new), `src/kaleta/services/setup_service.py`,
the setup view and `src/kaleta/views/categories*`, `src/kaleta/i18n/locales/*.json`,
`docs/bdd.md`.

## Open questions

- Templates as TOML files in the repo or as Python data? Default: TOML — readable and
  reviewable by non-developers, loaded and validated by a Pydantic schema.
- Should a template also seed budgets? Default: no amounts — a hint shown in the budget
  builder, since a template does not know the user's income.
- Does "Company" belong in a personal budget, or should a company be its own family
  (tenant)? Default: categories only, for a sole trader who keeps both in one ledger;
  record the trade-off.
