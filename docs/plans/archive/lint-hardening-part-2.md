---
plan_id: lint-hardening-part-2
title: Lint hardening Part 2 — more ruff families, stricter mypy, money-type guard
area: ci
effort: small
status: archived
archived_at: 2026-10-21
roadmap_ref: ../../roadmap.md
---

# Lint hardening Part 2

## Intent
Part 1 (`archive/lint-hardening.md`) consolidated bandit into ruff's `S` family
and set the current selection. This adds the ruff rule families and mypy error
codes that are **clean or a handful of fixes away** on the current tree and carry
real signal for an async-SQLAlchemy / Pydantic / finance codebase — plus a
concrete guard that monetary columns are never stored as `Float` (the convention
is `Numeric`/`Decimal`, but nothing enforced it).

Deliberately deferred to their own work (too large / opinionated for this PR):
`DTZ` (~110, tz-aware datetimes), `TC` (~343, `TYPE_CHECKING` import moves — and
import-linter already excludes type-only imports), `TRY` (~199, exception style
that partly conflicts with the `kaleta.exceptions` convention).
`unused-awaitable` is **rejected**: it flags ~249 SQLAlchemy false positives, so
adopting it would mean blanket `# type: ignore` (green-washing). The mypy
`warn_unreachable`, `truthy-bool` and `redundant-expr` checks are **also
deferred** — on investigation they almost only surface the "declared
non-optional but runtime-optional" gap (SQLAlchemy relationships, NiceGUI
context, outer-join rows), i.e. legitimate defensive guards, not bugs; adopting
them now would mean ~10 ignores on correct code.

## Scope
- ruff `lint.select`: add `ASYNC`, `G`, `LOG`, `TID`, `ISC`, `FLY`, `RSE`,
  `PLE`, `C4`, `PIE`, `RET`, `SLF`, `PERF`.
- ruff `flake8-tidy-imports.banned-api`: ban `sqlalchemy.Float` / `REAL` /
  `Double` so amounts cannot be stored as binary floats. The one legitimate
  non-money float column (`payee_merge.MergeHistory.score`, a 0..1 similarity)
  keeps a documented `# noqa: TID251`.
- mypy: `enable_error_code` adds `possibly-undefined` and `ignore-without-code`
  (both clean on the tree). `warn_unreachable` / `truthy-bool` / `redundant-expr`
  are deferred (see Intent).
- Fix the violations these surface (ruff ~27 small). No behaviour change; any
  production edit is a lint fix, called out in notes.
- Fix the 5 pre-existing `api/v1` `return-value` errors that the mypy config
  change unmasks (see notes) — required for the gate to be green.

## Not in scope
- `DTZ`, `TC`, `TRY`, `unused-awaitable`, `warn_unreachable`, `truthy-bool`,
  `redundant-expr` (see Intent).
- Type-checking `tests/` and `scripts/` (mypy still runs on `src/` only).
- A per-column "amount must be Numeric" audit test (the `Float` ban covers the
  real risk; a name-based audit is a possible follow-up).

## Acceptance criteria
- `grep -q '"ASYNC"' pyproject.toml`
- `grep -q 'banned-api' pyproject.toml`
- `grep -q 'ignore-without-code' pyproject.toml`
- `uv run ruff check .`
- `uv run mypy src/`
- `./scripts/verify.sh`

## Touchpoints
`pyproject.toml` (ruff + mypy config), plus small lint fixes across `src/`,
`scripts/` and `tests/` (logging calls, comprehensions, returns, private
access, perf, `dict()` literals) and one `# noqa: TID251` in
`src/kaleta/models/payee_merge.py`.

## Implementation notes
- **ruff families added** (`ASYNC G LOG TID ISC FLY RSE PLE C4 PIE RET SLF PERF`).
  Fixes: comprehensions/`extend` for PERF401 (manual list-append loops),
  logging-outside-except (LOG004), and friends — all autofixed or small rewrites.
  Two documented suppressions: `payee_merge.py` `# noqa: TID251` (the `score`
  column is a 0..1 similarity, legitimately `Float`, not money) and one
  `# noqa: PERF401` on a large display-row dict where a comprehension reads worse.
- **banned-api money guard**: `sqlalchemy.Float`/`REAL`/`Double` are banned so
  amounts can't be stored as binary floats. `alembic/versions/**` is exempted
  (TID251) — migrations record the historical schema verbatim, including that
  one legit Float score column.
- **SLF001**: ignored in `tests/**` (tests legitimately poke internals); the 4
  `src/` hits got documented `# noqa: SLF001` (NiceGUI `_create_user_storage`,
  SQLAlchemy `Row._mapping`, this view's own `_loading` guard) — all intentional
  internal access with no public alternative.
- **mypy codes**: added `possibly-undefined` + `ignore-without-code` (both clean).
  Dropped `warn_unreachable`/`truthy-bool`/`redundant-expr` after they only
  surfaced defensive guards on the non-optional-but-runtime-None idiom (deferred).
- **Latent issue found & fixed**: any change to `[tool.mypy]` invalidates mypy's
  incremental cache, and a *fresh* strict run reveals 5 pre-existing
  `return-value` errors in `api/v1/{transactions,payees,institutions,categories,
  budgets}.py` — the `update_*` endpoints return an ORM `Model | None` that
  FastAPI serialises via `response_model`, exactly like their sibling
  `create/get/list` endpoints which all carry `# type: ignore[return-value]`.
  The `update_*` ones were simply missing that ignore; added it (with the code,
  so `ignore-without-code` is satisfied). These were masked on `main` only by a
  stale `.mypy_cache`. Logged to chores so the maintainer can decide whether to
  type these returns properly.

## Implementation

Landed on 2026-10-21.

| SHA | Author | Date | Message |
|---|---|---|---|
| `1082235` | Dawid (Ani) | 2026-10-13 | ci: lint hardening part 2 — more ruff families, mypy codes, money-type guard |
| `5718fd8` | Dawid (Ani) | 2026-10-13 | ci: widen money guard + plan touchups (review nits) |

**Files changed:**
- docs/plans/chores.md
- docs/plans/lint-hardening-part-2.md
- pyproject.toml
- scripts/benchmark_forecast_fallback.py
- scripts/check_doc_links.py
- src/kaleta/api/errors.py
- src/kaleta/api/v1/budgets.py
- src/kaleta/api/v1/categories.py
- src/kaleta/api/v1/institutions.py
- src/kaleta/api/v1/payees.py
- src/kaleta/api/v1/transactions.py
- src/kaleta/auth/session.py
- src/kaleta/db/audit.py
- src/kaleta/debug_info.py
- src/kaleta/models/payee_merge.py
- src/kaleta/seeders/__init__.py
- src/kaleta/seeders/budgets.py
- src/kaleta/services/budget_service.py
- src/kaleta/services/category_service.py
- src/kaleta/services/currency_rate_service.py
- src/kaleta/services/data_encryption_service.py
- src/kaleta/services/planned_transaction_service.py
- src/kaleta/services/reserve_fund_service.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/reports_canned/cash_flow.py
- src/kaleta/views/reports_canned/income_statement.py
- src/kaleta/views/reports_canned/scaffold.py
- src/kaleta/views/transactions/edit_dialog.py
- tests/unit/schemas/test_budget_schema.py
- tests/unit/schemas/test_transaction_schema.py
- tests/unit/services/test_planned_transaction_service.py
- tests/unit/services/test_reserve_fund_service.py
- tests/unit/services/test_transaction_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| `grep -q '"ASYNC"' pyproject.toml` | 0 |
| `grep -q 'banned-api' pyproject.toml` | 0 |
| `grep -q 'ignore-without-code' pyproject.toml` | 0 |
| `uv run ruff check .` | 0 |
| `uv run mypy src/` | 0 |
| `./scripts/verify.sh` | skipped (--fast; green at implementation time) |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
