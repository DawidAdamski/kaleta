---
plan_id: errors-i18n-core-cohort
title: Localize rule, subscription, category, budget & account error toasts
area: cross-cutting
effort: small
status: archived
archived_at: 2026-10-23
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Localize rule, subscription, category, budget & account error toasts

## Intent
A follow-up cohort slice of
[`errors-i18n-message-keys`](errors-i18n-message-keys.md), which
shipped the carrier (`KaletaError.message_key` + `params`), the
`error_handling.resolve_toast_text` wiring, and migrated the first cohort
(payee identity / merge-undo); later slices migrated `transaction_service`,
the funds/salary/debt family, and `irregular_item_service`. This slice
migrates the **core-CRUD family** — five services — so a Polish session
reads their toasts in Polish, while logs, event capture and the API keep
reading the English `exc.message`.

## Scope
Covers — each user-facing `KaletaError` raise in these five services gets a
`message_key` (+ `params` where the message interpolates), keeping the
existing English string byte-identical as the positional `message` fallback:
- `src/kaleta/services/rule_service.py` → `errors.rule.*`
- `src/kaleta/services/subscription_service.py` → `errors.subscription.*`
- `src/kaleta/services/category_service.py` → `errors.category.*`
- `src/kaleta/services/budget_service.py` → `errors.budget.*`
- `src/kaleta/services/account_service.py` → `errors.account.*`
- The five new sub-blocks in `en.json` and `pl.json`, placed at the END of
  the `errors` object (after `irregular_item`).
- `docs/bdd.md`: `KAL-ERR-005` + a covering integration test
  (`tests/integration/test_error_i18n_core_cohort.py`).

Does NOT cover:
- Any other service (each remaining service gets its own follow-up slice —
  the `chores.md` follow-up line stays open until all are done).
- Changing `code` values, control flow or any behaviour.
- The REST API error contract (still emits the English `message`). The
  category service is also reached from `api/v1/categories.py`; migrating the
  view path's toasts helps the UI and leaves the API's English message
  untouched.
- The plain-`Exception` form errors (`SubscriptionFormError`), which are not
  `KaletaError` and out of this carrier's scope.
- Post-commit / invariant `KaletaError` raises no user action can hit (see
  Implementation notes).

## Acceptance criteria
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run python scripts/spec_coverage.py`
- `uv run python scripts/check_doc_links.py`
- `grep -q "KAL-ERR-005" docs/bdd.md`
- `uv run pytest tests/integration -k "error_i18n" -n 2 -m "not slow"`

## Touchpoints
- `src/kaleta/services/rule_service.py` — migrated raises.
- `src/kaleta/services/subscription_service.py` — migrated raises.
- `src/kaleta/services/category_service.py` — migrated raises.
- `src/kaleta/services/budget_service.py` — migrated raises.
- `src/kaleta/services/account_service.py` — migrated raises.
- `src/kaleta/i18n/locales/en.json`, `pl.json` — `errors.rule.*`,
  `errors.subscription.*`, `errors.category.*`, `errors.budget.*`,
  `errors.account.*`.
- `docs/bdd.md` — `KAL-ERR-005`;
  `tests/integration/test_error_i18n_core_cohort.py`.

## Open questions
- Resolved to plan defaults (no user input while armed).

## Implementation notes
- **Slice boundary.** This covers the five core-CRUD services only; the
  parent plan's "remaining services get their own follow-up slices" is
  honoured. The `chores.md` follow-up line stays unticked.
- **Per-service caller search (reachability).** Every migrated raise reaches
  a view (→ `notify_kaleta_error`) directly or through a view-called service.
  - **`RuleService`** — callers: `views/rules.py` (`list`, `delete`),
    `views/transactions/edit_dialog.py` (`create`, `suggest_from_corrections`),
    `api/v1/*` (import rules are a different service). The rule dialog reaches
    `create`/`update`, which run `_require_category`. **Migrated 6 raises,
    skipped 0 `KaletaError`.** Keys: `pattern_empty` (two raise sites —
    `create` and `update`); `only_contains_mode` (two raise sites — `create`
    and `update`); `rule_not_found` (`{rule_id}`); `category_not_found`
    (`{category_id}`). (4 keys over 6 raises.) The two `RuntimeError`
    "missing right after commit/update" raises are **not** `KaletaError`
    (post-commit invariants no user action can hit) — left as-is.
  - **`SubscriptionService`** — callers: `views/subscriptions/dialogs.py`
    (`count_refilable`, `refile`, `create_planned_from_candidate`),
    `views/subscriptions/page.py`, `api/v1/subscriptions.py`. All 5
    `KaletaError` raises sit on view-reached methods. **Migrated 5, skipped
    0.** Keys: `candidate_needs_account`; `planned_needs_name`;
    `planned_needs_positive_amount`; `not_found` (`{sub_id}`, two raise sites
    — `refile` and `count_refilable`). (4 keys over 5 raises.) The module's
    `SubscriptionFormError` raises are a plain `Exception`, out of scope.
  - **`CategoryService`** — callers: many views (`categories.py`,
    `budget_builder.py`, …) plus `api/v1/categories.py`. The category editor
    reaches `create`/`update` (→ `_assert_type_matches_parent`,
    `_assert_unique_name`) and `delete`. **Migrated 4 user-facing raises,
    skipped 1.** Keys: `parent_not_found` (`{parent_id}`);
    `type_must_match_parent` (`{category_type}`, `{parent_type}`);
    `name_exists` (`{name}`); `subscriptions_root_protected`. **Skipped:** the
    bare `KaletaError("Category id={category.id} not found after commit")` in
    `create` — a post-commit invariant (the row was just inserted and
    committed) that no user action can reach; left English without a key, like
    the equivalent post-commit guard in `transaction_service.create`.
  - **`BudgetService`** — callers: `views/budget_plan/grid.py`
    (`load_annual_plan_grid` → `split_plan_years`), `views/budgets/*`,
    `api/v1/budgets.py`. The annual-plan grid reaches `split_plan_years`
    through `load_annual_plan_grid`. **Migrated 1, skipped 0.** Key:
    `year_required`.
  - **`AccountService`** — callers: many views plus `api/v1/accounts.py`. The
    importer reaches `find_by_external_number`
    (`views/import_view/page.py`), which raises on an ambiguous suffix match.
    **Migrated 1, skipped 0.** Key: `ambiguous_external_number`.
- **No-period fallbacks preserved.** `subscription.*` and
  `category.parent_not_found` keep their original trailing-period-less
  English wording byte-identical; the test asserts `t(key, **params) ==
  exc.message`.
- **`code` values preserved.** No raise changed its `code`; only
  `message_key`/`params` were added. No behaviour or `code` change.
- **i18n placement.** The five sub-blocks are appended at the end of the
  `errors` object (after `irregular_item`), clustered.
- **View changes.** None — all five are services. The test is
  integration-only and touches no file under `src/kaleta/views/`.

## Implementation

Landed on 2026-10-23.

| SHA | Author | Date | Message |
|---|---|---|---|
| `67792f6` | Dawid (Ani) | 2026-10-23 | feat(errors): localize rule, subscription, category, budget & account error toasts |

**Files changed:**
- docs/bdd.md
- docs/plans/README.md
- docs/plans/errors-i18n-core-cohort.md
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/services/account_service.py
- src/kaleta/services/budget_service.py
- src/kaleta/services/category_service.py
- src/kaleta/services/rule_service.py
- src/kaleta/services/subscription_service.py
- tests/integration/test_error_i18n_core_cohort.py
