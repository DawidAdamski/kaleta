---
plan_id: rules-tags-api
title: Categorisation rules and tags REST API: list, get, create, update, delete
area: api, rules, tags
effort: medium
status: archived
archived_at: 2026-11-16
roadmap_ref: ../../roadmap.md
---

# Categorisation rules and tags REST API: list, get, create, update, delete

## Intent
`RuleService` (`src/kaleta/services/rule_service.py`) and `TagService`
(`src/kaleta/services/tag_service.py`) are only reachable from the UI (`views/rules.py`,
`views/tags.py`, `views/transactions/edit_dialog.py`). An API client can set `tag_ids` on a
transaction (`TransactionCreate.tag_ids`), but it cannot list tags to find those ids. It
also cannot add the rule that would categorise the next import. Expose both services over
`/api/v1`. Use paths that cannot be confused with the existing `/import-rules`
(filename → account, `ImportRuleService`): **`/categorisation-rules`** and **`/tags`**.

## Scope

### Tags: new router `src/kaleta/api/v1/tags.py`, prefix `/tags`, OpenAPI tag "Tags"
- `GET /tags/` → `list[TagResponse]` (`TagService.list()`, already name-ordered via `by_name`).
- `GET /tags/{tag_id}` → `TagResponse`, 404 if `TagService.get` returns `None`.
- `POST /tags/` (`TagCreate`) → 201 `TagResponse`.
- `PUT /tags/{tag_id}` (`TagUpdate`, partial: `exclude_unset`) → `TagResponse`. 404 when
  `TagService.update` returns `None`.
- `DELETE /tags/{tag_id}` → 204. 404 when `TagService.delete` returns `False`. The
  `transaction_tags` rows go with it (FK `ondelete="CASCADE"` on `tag_id`). The
  transactions themselves are not touched. The test asserts this.
- `TagResponse` (`schemas/tag.py`, `from_attributes=True`) maps the ORM `Tag` directly with
  `model_validate`. No new response schema is needed. `expire_on_commit=False`
  (`db/session.py`), so the object `create` returns can be read without a refresh.

### Tag validation: NEW service logic in `TagService`
Today the service does none of this:
- **Duplicate name → 409.** `Tag` has `UniqueConstraint("name_bidx", name="uq_tags_name_bidx")`,
  with `name_bidx = exact_index(name)` (exact, case-sensitive: "Wakacje" and "wakacje" are
  different names). `TagService.create`/`update` do not check it, so a duplicate reaches the
  DB as an `IntegrityError` and becomes a 500. Add a pre-check in the service, following
  `PayeeService._check_merge_name` (`select(Tag.id).where(Tag.name_bidx == exact_index(name))`,
  excluding the tag's own id on update). On a clash, raise
  `ConflictError(f"A tag named '{name}' already exists")`.
- **Blank name → 422.** `TagCreate.name` has no `min_length`, so `""` and `"   "` are accepted
  today. Strip the name in the service and raise `ValidationError` when it is empty, on create
  and on update.
- **Explicit `null` name on update → 422.** `TagUpdate.name` is `str | None`. A body
  `{"name": null}` currently does `setattr(tag, "name", None)` on a `nullable=False` column,
  which gives a 500. Raise `ValidationError` instead. `color`, `icon` and `description` stay
  nullable: `null` clears them, as today.
- Raise without `message_key` (localisation is opt-in per raise site, see
  `KaletaError`). This plan does not touch the views or the locale files.

### Categorisation rules: new router `src/kaleta/api/v1/categorisation_rules.py`, prefix `/categorisation-rules`, OpenAPI tag "Categorisation rules"
- `GET /categorisation-rules/` → `list[CategorisationRuleResponse]`, with optional query
  `active_only: bool = False` passed to `RuleService.list(active_only=)`. Order as the
  service gives it: `priority desc, id asc`.
- `GET /categorisation-rules/{rule_id}` → 404 if `RuleService.get` returns `None`.
- `POST /categorisation-rules/` (`CategorisationRuleCreate`) → 201.
- `PUT /categorisation-rules/{rule_id}` (`CategorisationRuleUpdate`, partial). The service
  already raises `NotFoundError` for a missing rule, and the error envelope turns it into 404.
- `DELETE /categorisation-rules/{rule_id}` → 204. 404 when `RuleService.delete` returns `False`.
- **Response mapping:** `RuleService` returns ORM `CategorisationRule` rows with `category`
  loaded through `selectinload`. `CategorisationRuleResponse.category_name` is not a model
  attribute, so add a `_to_response(rule)` helper in the router, as `import_rules.py` does:
  `category_name=rule.category.name if rule.category else None`. No new response schema.
- **Category existence is already checked in the service.** `RuleService._require_category`
  raises `NotFoundError(message_key="errors.rule.category_not_found")` on create, and on
  update when `category_id` is given. Through the envelope this is **404** (code
  `not_found`), the same as `CategoryService`'s `errors.category.parent_not_found`. Keep it.
  See Open questions. Declare 404 in the route's `responses`.
- Blank pattern (`"   "`) already raises `ValidationError` → 422. `match_mode` only has
  `CONTAINS`, so a different value is refused by Pydantic (422) before it reaches the service.

### Rule validation: NEW service logic in `RuleService.update`
- **Explicit `null` on a non-nullable field → 422.** `CategorisationRuleUpdate` makes every
  field `| None`. `pattern: null` is already refused (`(None or "").strip()` → empty →
  `ValidationError`). `category_id: null` skips `_require_category` and is then `setattr` to
  `None`. `match_mode`, `is_active` and `priority` set to `null` are also written straight
  through. All four columns are `nullable=False`, so each is a 500 today. Raise
  `ValidationError` naming the field. No message key, as above.
- **Probably stale `category_name` after a category change: verify, then fix in the
  service.** `update` sets `rule.category_id` on an instance whose `category` relationship is
  already loaded. The re-read `self.get(rule_id)` returns the same identity-map object, and
  `selectinload` does not overwrite an already-loaded relationship without `populate_existing`.
  So the response may still carry the *old* category name. If
  `test_update_rule_category_returns_new_category_name` fails, fix it in `RuleService.update`
  (for example `await self.session.refresh(rule, ["category"])` after the commit, or
  `.execution_options(populate_existing=True)` in `get`). Record which fix was used. The UI
  re-lists after a save, so this has not shown up there.

### Rule suggestion: read-only, exposed
- `POST /categorisation-rules/suggestions`, body: new schema
  `CategorisationRuleSuggestionRequest` (`payee_name: str | None = None`,
  `description: str = Field(default="", max_length=500)`, `category_id: int`) →
  `CategorisationRuleSuggestion | None` (200, `null` when there is no offer).
  The route calls `RuleService.suggest_from_corrections(payee_name=, description=, category_id=)`.
- Why it is safe to expose: the method's docstring says "Never creates a rule". It only runs
  SELECTs: `_find_rule_by_pattern` reads all rules, and `_count_matching_categorisations`
  reads the payee name and description of every transaction in that one category, then
  decrypts and substring-matches them in Python. The cost is linear in that category's
  transaction count, the same work the edit dialog does on every re-categorisation. It needs
  no extra limit.
- A POST with a body, not a GET with query params: payee names and descriptions are
  encrypted at rest and must not end up in URLs or access logs.
- Declare the route before the `/{rule_id}` routes.
- An unknown `category_id` returns `null` (the service returns `None` when
  `session.get(Category, …)` misses). Keep that. It is a "no offer" answer, not an error.

### Wiring
- Register both routers in `src/kaleta/api/v1/__init__.py`. Every handler takes
  `session: AsyncSession = Depends(get_session)` with `get_session` imported from
  `kaleta.api.deps` (guarded by `test_api_tenant_isolation_guard.py`).
- Every operation has a `summary`. Routes stay thin: no validation in the router beyond
  None → 404 for `get`/`delete`/tag `update`.

### Scenario (paste into `docs/bdd.md`, Feature: Public API, after KAL-API-009)

```gherkin
  KAL-API-015 @automated
  Scenario: Manage tags and categorisation rules through the API
    Given a valid API bearer token
    And an account "mKonto" and the expense categories "Spożywcze" and "Alkohol"
    When I POST a tag named "Wakacje" with color "#2E7D32" to /api/v1/tags
    Then the response is 201 and GET /api/v1/tags lists "Wakacje"
    And a second tag named "Wakacje" is refused with 409
    And a tag named "   " is refused with 422
    When I PUT the name "Urlop 2026" to that tag
    Then GET /api/v1/tags/{id} returns the name "Urlop 2026" and the color "#2E7D32"
    And a PUT with name null is refused with 422
    Given an expense of 54.30 PLN on "mKonto" dated 2026-11-14, described "Hotel Sopot" and tagged "Urlop 2026"
    When I DELETE the tag
    Then the response is 204, GET /api/v1/tags no longer lists it
    And the expense of 54.30 PLN still exists, without tags
    When I POST a categorisation rule with pattern "LIDL", category "Spożywcze" and priority 10 to /api/v1/categorisation-rules
    Then the response is 201 with category_name "Spożywcze", match_mode "contains" and is_active true
    And a rule for category id 999999 is refused with 404
    And a rule with pattern "   " is refused with 422
    When I PUT category "Alkohol" and is_active false to that rule
    Then the response has category_name "Alkohol" and is_active false
    And GET /api/v1/categorisation-rules?active_only=true does not list it
    And a PUT with is_active null is refused with 422
    When I DELETE the rule
    Then the response is 204 and a second DELETE is 404
    Given four expenses on "mKonto" described "LIDL WARSZAWA", without a payee, filed under "Spożywcze"
    When I POST description "LIDL WARSZAWA" and category "Spożywcze" to /api/v1/categorisation-rules/suggestions
    Then the response is 200 with pattern "LIDL WARSZAWA", category_name "Spożywcze" and match_count 4
    And GET /api/v1/categorisation-rules is still empty
    And with only three such expenses the response is null
    And GET /api/v1/import-rules is still empty
```

### Out of scope
- Showing tags on `TransactionResponse`. It has no `tags`/`tag_ids` field today, so a client
  cannot read back which tags a transaction carries. A `tag_ids` filter on
  `GET /transactions` is also out (the service supports one in `_build_filters`, the route
  does not). Separate plan.
- `TransactionService._load_tags` silently drops unknown `tag_ids`, while the transactions
  route description says they "must reference existing tag IDs". Chore inbox, not this plan.
- A uniqueness rule for categorisation-rule patterns. Duplicates stay allowed, as in the UI.
  See Open questions.
- Re-applying rules to existing transactions, rule `match_mode`s beyond `contains`, and
  rule application from the API outside `/imports`.
- Any view change. `views/tags.py` `_save` does not catch `KaletaError`, so after this plan a
  duplicate name in the UI raises an unhandled `ConflictError` instead of an unhandled
  `IntegrityError`. Wrapping it with `notify_kaleta_error` is a view change (needs `--e2e`).
  Add it to `docs/plans/chores.md` instead.
- i18n `message_key`s for the new raises (no view surfaces them yet).
- Category deletion behaviour. Rules on a deleted category disappear through
  `categorisation_rules.category_id` `ondelete="CASCADE"`. That is unchanged; mention it in
  the router description of `DELETE /categories` only if it is touched anyway (it is not).

## Acceptance criteria
- `uv run pytest tests/integration/test_api_rules_tags.py -q`
- `uv run pytest tests/integration/test_api_tenant_isolation_guard.py -q`
- `uv run pytest tests/unit/services/test_rule_service.py -q`
- `uv run pytest tests/integration/test_categorisation_rules.py -q`
- `uv run pytest tests/integration/test_error_i18n_core_cohort.py -q`
- `grep -c "KAL-API-015" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`
- Tests in the new module (each docstring `Covers: KAL-API-015`), literals taken from the
  scenario: `test_tag_crud_round_trip` (create "Wakacje" #2E7D32 → list → rename "Urlop
  2026" → get), `test_duplicate_tag_name_is_409`, `test_blank_tag_name_is_422`,
  `test_null_tag_name_on_update_is_422`, `test_tag_404s` (get/put/delete of an unknown id),
  `test_deleting_a_tag_keeps_its_transactions` (54.30 PLN 2026-11-14 "Hotel Sopot" survives,
  with its `transaction_tags` row gone. Check it through the DB/service, because
  `TransactionResponse` has no tags).
- Rule tests: `test_rule_crud_round_trip` ("LIDL" → "Spożywcze", priority 10, `match_mode`
  "contains", `is_active` true), `test_rule_unknown_category_is_404` (999999),
  `test_blank_rule_pattern_is_422`, `test_update_rule_category_returns_new_category_name`
  ("Alkohol"), `test_active_only_filter_hides_inactive_rule`,
  `test_null_fields_on_rule_update_are_422` (`category_id`, `match_mode`, `is_active`,
  `priority` each set to null), `test_rule_delete_twice_is_404`.
- Suggestion tests: `test_suggestion_after_four_categorisations` ("LIDL WARSZAWA",
  "Spożywcze", `match_count` 4, and no rule created), `test_no_suggestion_below_threshold`
  (three expenses → `null`).
- Separation and docs tests: `test_rules_api_does_not_touch_import_rules`
  (`GET /api/v1/import-rules/` stays `[]`), and
  `test_openapi_gives_every_rule_and_tag_operation_a_summary` (assert on `app.openapi()`
  for every `/api/v1/tags` and `/api/v1/categorisation-rules` operation).
- Verification: `./scripts/verify.sh` passes (the short gate is enough: no view changes).

## Touchpoints
- `src/kaleta/api/v1/tags.py` (new), `src/kaleta/api/v1/categorisation_rules.py` (new),
  `src/kaleta/api/v1/__init__.py` (register both routers)
- `src/kaleta/services/tag_service.py`: duplicate-name check (`Tag.name_bidx`,
  `kaleta.db.types.exact_index`), blank and null name validation, raising `ConflictError` /
  `ValidationError`
- `src/kaleta/services/rule_service.py`: null-field validation in `update`; stale
  `category` relationship fix if the test shows it
- `src/kaleta/schemas/categorisation_rule.py`: add `CategorisationRuleSuggestionRequest`
  (and to `__all__`)
- `tests/integration/test_api_rules_tags.py` (new). Use `api_client`, `create_account` and
  `create_category` from `tests/integration/conftest.py`
- `docs/bdd.md` (KAL-API-015), `docs/plans/chores.md` (tags dialog does not catch
  `KaletaError`; `_load_tags` drops unknown ids)

## Open questions
- **Unknown `category_id` on a rule: 404 or 422?** The subscriptions API chose 422 for a bad
  body reference. `RuleService._require_category` raises `NotFoundError` (404), like
  `CategoryService`'s parent check, and `test_error_i18n_core_cohort.py` exercises it as a
  `NotFoundError`. Default: **keep 404**, and document it in the route `responses`. No
  service change.
- **Duplicate rule pattern: 409?** There is no constraint, and the UI allows two rules with
  one pattern (priority decides). `suggest_from_corrections` already skips offering a pattern
  that exists. Default: **allow duplicates** (201). Do not add a check.
- **Tag name case:** should "wakacje" clash with "Wakacje"? The DB constraint is on
  `exact_index` (case-sensitive), the same as payees. Default: **exact match only**, the
  same as the constraint.
- **Suggestion response when there is no offer:** 200 with `null`, or 204? Default:
  **200 `null`** (`response_model=CategorisationRuleSuggestion | None`). One status keeps
  clients simple.
- **Expose `suggest_from_corrections` at all?** Default: **yes**, as above. It is read-only,
  and its cost is bounded by one category's transactions.
- **Scenario id:** Default **KAL-API-015**. KAL-API-010 to 014 are taken by other API plans.

## Implementation notes
- **Scenario id:** KAL-API-015, after KAL-API-012 in `docs/bdd.md` (013 and 014 are on open
  branches; the scenarios will be re-ordered when they merge).
- **Paths:** `/tags` and `/categorisation-rules` (new routers `api/v1/tags.py`,
  `api/v1/categorisation_rules.py`); `POST /categorisation-rules/suggestions` is declared
  before the `/{rule_id}` routes.
- **Tag names:** `TagService._checked_name` strips the name, refuses a blank or `null` one
  (422) and refuses another tag's exact name (409, `ConflictError`) — the same exact match as
  `uq_tags_name_bidx`, so "wakacje" and "Wakacje" may coexist. A tag keeps its own name on
  update. Names are now stored stripped (create and update).
- **Rule nulls:** `RuleService.update` refuses `null` for `category_id`, `match_mode`,
  `is_active` and `priority` (422) before touching the row; `pattern: null` was already
  refused.
- **Stale `category_name` confirmed:** `test_update_rule_category_returns_new_category_name`
  failed with "Spożywcze" instead of "Alkohol". Fixed in `RuleService.get` with
  `.execution_options(populate_existing=True)`, so the re-read after `update` replaces the
  loaded relationship.
- **Unknown category on a rule:** stays 404 (`NotFoundError` from `_require_category`),
  documented in the routes' `responses`.
- **Duplicate rule patterns:** allowed, as in the UI.
- **Suggestion with no offer:** 200 `null`.
- **Chores:** the tags dialog not catching `KaletaError`, and `_load_tags` dropping unknown
  ids, are in `docs/plans/chores.md`.

## Implementation

Landed on 2026-11-16 (PR #436).

| SHA | Author | Date | Message |
|---|---|---|---|
| `3956abd1` | Dawid Adamski | 2026-11-16 | Merge pull request #436 from DawidAdamski/plan/rules-tags-api |

**Files changed:**
- docs/bdd.md
- docs/plans/chores.md
- docs/plans/rules-tags-api.md
- src/kaleta/api/v1/__init__.py
- src/kaleta/api/v1/categorisation_rules.py
- src/kaleta/api/v1/tags.py
- src/kaleta/schemas/categorisation_rule.py
- src/kaleta/services/rule_service.py
- src/kaleta/services/tag_service.py
- tests/integration/test_api_rules_tags.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
