---
plan_id: category-templates
title: Category templates for who you are — single, family, company, car, home — combined
area: setup / categories
effort: large
status: in-progress
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
- **Company adds business subscription groups** (requested after `subscriptions-categories`):
  the Subscriptions tree (ADR-28) ships only personal purpose children (Streaming, Muzyka…).
  Applying the Company template adds *firmowe* purpose children under the same subscriptions
  root so a sole trader's abonamenty group by business purpose, not mixed into the personal
  ones: **Hosting i domeny / Hosting & domains**, **Oprogramowanie firmowe / Business
  software**, **Księgowość i fakturowanie / Accounting & invoicing**, **Marketing i reklama /
  Marketing & ads**. They are added by the same blind-index, idempotent path as the personal
  children (`CategoryService.ensure_subscriptions_root_and_children` / the template service),
  so re-applying adds nothing and the panel's "By category" card groups them automatically.
  "2 companies" (repeatable) does *not* duplicate these — a firm's subscription purpose is
  shared across its copies — only the firm's own expense/income subtree repeats. A user who
  never picks Company keeps a clean personal subscriptions tree.
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
`src/kaleta/services/category_service.py` (the subscriptions root, for the Company template's
business subscription children), the setup view and `src/kaleta/views/categories*`,
`src/kaleta/i18n/locales/*.json`, `docs/bdd.md`.

## Open questions

- Templates as TOML files in the repo or as Python data? Default: TOML — readable and
  reviewable by non-developers, loaded and validated by a Pydantic schema.
- Should a template also seed budgets? Default: no amounts — a hint shown in the budget
  builder, since a template does not know the user's income.
- Does "Company" belong in a personal budget, or should a company be its own family
  (tenant)? Default: categories only, for a sole trader who keeps both in one ledger;
  record the trade-off.

## Implementation notes

### Delivery in two slices (PRs)

- **Slice 1 — the engine (this PR)**: the TOML catalogue + `CategoryTemplateService`
  (list / preview / apply), merging by blind index, repeatable copies, and the Company →
  Subscriptions-tree seeding. Service + data + tests + BDD only — no views, so the short
  gate applies.
- **Slice 2 — the UI (done)**: the template picker with its preview dialog on
  `/categories`; rewires `views/categories.py` onto the new service and retires the old
  flat JSON templates. Views → `--e2e` gate + i18n. See *Decisions (Slice 2 — the UI)* below.

### Decisions (Slice 1)

- **A primitive template system already existed** and stayed through Slice 1: flat JSON
  (`single-person`, `polish-household`, `freelancer`, `student`) under
  `data/category_templates/`, with `CategoryService.{list,preview,apply}_template` adding
  only root names, wired into `views/categories.py`. Slice 1 added a *new*, richer system
  beside it (`*.toml` + `CategoryTemplateService`) so the view kept working; Slice 2 removed
  the old one.
- **TOML, loaded by `tomllib`** (open question resolved — no new dependency; Python 3.13
  stdlib), validated by `schemas/category_template.py` (Pydantic). Each template is one
  file: `key`, `name`/`name_en`, `order`, `repeatable`, `[[groups]]` (a parent + its
  children, per type, both languages), and optional `subscriptions`/`subscriptions_en`.
  **Gotcha recorded**: a bare TOML key after a `[[groups]]` header binds to that table, so
  `subscriptions` must sit *above* the groups.
- **Combining by blind index**: `apply` ensures each parent (root of its type) then each
  child, matching existing rows by `exact_index(name)`, so a parent shared by two
  templates — or a re-run — is reused, never duplicated. The catalogue carries both
  languages; the caller passes `language` (the Slice 2 view uses the family's), default
  Polish for this Polish-first app.
- **Repeatable multiples**: a `repeatable` template applied with a `copy_name` suffixes its
  parents — `Samochód` → `Samochód: Skoda` — so two cars are two subtrees. Children and the
  Company subscription purposes are *not* suffixed; the subscription purposes are shared
  across company copies (added once by blind index), matching #219.
- **Company belongs in the personal ledger** (open question): categories only, for a sole
  trader who keeps both in one ledger — no separate tenant. Its business purposes also seed
  the Subscriptions tree, via `CategoryService.ensure_subscriptions_root_and_children`
  (creating the tree in the family's language first if absent).
- **Budgets**: not seeded (open question default kept); a `budget_hint` field is **not**
  added in Slice 1 — deferred until the budget builder consumes it.

### Review fixes (Slice 1)

- **Preview counts by name-path, not DB id.** `planned` is keyed `("root", name, type)` /
  `("child", parent_name, child, type)` / `("sub", name)`. Keying on `parent_id` was wrong:
  a not-yet-created parent has `id=None`, so two new car copies' shared child "Paliwo"
  collided and the second read as already existing. Covered by a two-car preview test.
- **Company subscriptions are atomic and add only the 4 business purposes.** The apply
  creates a *bare* Subscriptions root (one transaction, no internal commit) when none
  exists, rather than calling `ensure_subscriptions_root_and_children` (which commits and
  seeds the 8 default purpose children). The tree's own default children are added later,
  in the family's language, when the Subscriptions page first runs `ensure_...` — it finds
  this root by its flag, so no second root. So `apply().created` and `preview` count only
  the template's own categories (incl. the 4 business purposes), never the tree defaults.
- **Language is the caller's.** Business purposes are added in the passed `language`; a tree
  already built in another language would mix (documented + tested). The Slice 2 view passes
  the family's language.
- **Blank `copy_name` is not a suffix.** `"  "` strips to empty → no `": "` suffix (would
  otherwise make "Samochód: "); tested.

### Decisions (Slice 2 — the UI)

- **One picker serves both "where"s.** The plan asked for first-run setup checkboxes *and*
  a Settings → Categories "Add from a template". In Kaleta the wizard's Setup card for
  categories links straight to `/categories`, so the picker lives there and is the
  first-run experience as well — no separate onboarding screen. The "Load template" button
  on `/categories` opens it; a returning user uses the same button to add a template later.
- **Multi-select, not one-at-a-time.** The picker is a checklist of all templates
  (`CategoryTemplateService.list()`); ticking several and applying once merges them by
  blind index (KAL-CTP-002). A repeatable template (car, company) shows a copy-name input;
  a second car is a second visit to the picker (idempotent — KAL-CTP-003/004).
- **Names from the catalogue, descriptions from i18n.** The template display names come from
  the TOML (`display_name(language)`) — the single source, already bilingual — so they are
  not duplicated into the locale files. Only the one-line descriptions and the picker/preview
  chrome are i18n keys (`categories.template_desc_<key>`, `template_picker_*`, etc.).
- **Language is the user's.** The view reads `app.storage.user["language"]` and passes it to
  `preview`/`apply`, so the Company template's business purposes land in the same language as
  the rest of the tree (closing the Slice 1 caveat).
- **Old flat JSON system retired.** Removed `CategoryService.{list,preview,apply}_template`,
  `_load_template`, `TemplatePreview`, `_TEMPLATE_DIR` and the `*.json` templates
  (`single-person`, `polish-household`, `freelancer`, `student`) plus their now-unused
  `template_name_*` / `template_skipped` i18n keys. The TOML catalogue + `CategoryTemplateService`
  is now the only template system.
- **E2e**: `tests/e2e/test_category_templates.py` (KAL-CTP-007) drives the picker — open,
  tick "Single", preview, apply, see "Housing"/"Rent" in the tree. Runs in English (the e2e
  app's language).
