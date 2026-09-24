---
plan_id: lint-hardening
title: Lint hardening — security rules in ruff, honest suppressions, pre-commit
area: infrastructure
effort: small
status: archived
archived_at: 2026-09-24
roadmap_ref: ../../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Lint hardening — security rules in ruff, honest suppressions, pre-commit

## Intent

An audit of the tooling (2026-09-22) found ruff and mypy configured well
and enforced in CI, and bandit installed but never run: it was in the
`dev` group and in the `security-auditor` agent's instructions, but not
in `ci.yml`, not in `scripts/verify.sh`, and had no configuration. The
security lint existed only when somebody asked an agent for it. Two
smaller findings: 130 `# noqa` comments in the tree silenced rules that
were never enabled (`ARG001`, `ANN001`, `PLW0603`, …), so they said
nothing and nothing flagged them; and `pre-commit` was a dependency
without a `.pre-commit-config.yaml`, so no check ran before a commit.

Make the security lint a gate that runs everywhere the other gates run,
by switching to ruff's port of bandit (`S`) instead of adding a second
tool; make every suppression in the tree answer for itself (`RUF100`);
give mypy the pydantic plugin; and add the pre-commit hooks so the gate
runs on the developer's machine before it runs in CI.

## Scope

- **Ruff rules** (`pyproject.toml`): add `S` and `RUF` to `select`.
  Ignore `RUF001`–`RUF003` globally — the prose is bilingual and uses
  typographic dashes and quotes on purpose. Per-file-ignores for what
  each tree legitimately does: `tests/**` asserts, holds fixture
  passwords, spawns the app and binds `0.0.0.0`; `scripts/**` holds the
  demo password and shells out; `alembic/versions/**` builds data
  migrations from literal table names; `src/kaleta/seeders/**` uses
  `random` for demo data.
- **Findings burned down**, not suppressed: the ten `assert x is not
  None` narrowings in `src/` become explicit `raise` (an `assert`
  disappears under `python -O`, and these guard reload-after-commit
  invariants); two `asyncio.create_task` calls without a held reference
  (`RUF006`, in `event_capture.py` and `subscriptions/dialogs.py`) keep
  one now, so a capture or a silent track cannot be garbage-collected
  mid-flight; one class-level mutable becomes a `ClassVar`
  (`ring_buffer.py`); five `int(round(…))` lose the redundant cast;
  `__all__` lists are sorted. The two `# nosec B608` markers in
  `backup_service.py` become `# noqa: S608` with the same reason; the
  two `urlopen` calls in `nbp_rate_service.py` carry `# noqa: S310`
  with the reason that the URL is a module-constant https address.
- **Suppressions**: `RUF100` removes the 130 `# noqa` comments that
  silenced nothing. One design note that rode on such a comment
  (`db/types.py`, the process-wide key source) is kept as a plain
  comment.
- **Bandit** leaves the `dev` group. The `security-auditor` agent runs
  the `S` rules with `--ignore-noqa` / `--isolated` instead, so its job
  becomes reviewing the suppressions rather than re-discovering what CI
  already gates. `deps-updater` no longer lists it.
- **mypy**: `plugins = ["pydantic.mypy"]`, so model constructors and
  `model_validate` calls are checked the way the runtime validates.
- **pre-commit**: `.pre-commit-config.yaml` with `repo: local` hooks
  through `uv run --no-sync`, so the hook uses the ruff / mypy /
  import-linter pinned in `uv.lock` rather than a mirror's version.
  `ruff check --fix --exit-non-zero-on-fix` and `ruff format` on
  `pre-commit`; `mypy src/` and `lint-imports` on `pre-push`.
  `AGENTS.md` and `CONTRIBUTING.md` say to install the hooks once per
  clone.
- **Docs**: `AGENTS.md` coding conventions name the `S` family, the
  `RUF100` rule and the no-`assert`-in-`src/` convention.

Out of scope:
- Widening mypy to `tests/` and `scripts/` — see Open questions; it is
  a burn-down of unknown size and gets its own PR once measured.
- Further rule families that the audit measured but did not enable:
  `ARG` (7), `PTH` (2), `C4` (2), `PERF` (14), `PLW` (19), `DTZ` (96,
  almost all `date.today()`, which is intended in a budgeting app),
  `FBT` (69). Any of them is one line in `select` when wanted.
- Aligning the local interpreter (3.14 in `__pycache__`) with the
  3.13 that CI and mypy pin.

## Acceptance criteria

- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run mypy src/`
- `uv run lint-imports`
- `uv run pytest tests/unit tests/integration -q`
- `uv lock --check`
- `grep -q '"S"' pyproject.toml`
- `grep -q '"RUF"' pyproject.toml`
- `grep -q 'pydantic.mypy' pyproject.toml`
- `test -f .pre-commit-config.yaml`
- `uv run pre-commit validate-config`
- `test "$(grep -rl nosec src/ | wc -l)" -eq 0`
- `test "$(grep -rnE '^\s*assert ' src/kaleta | wc -l)" -eq 0`
- `[manual]` `uv run ruff check . --select S --ignore-noqa --output-format concise` lists only the suppressions this plan justifies.

## Touchpoints

- `pyproject.toml` — ruff `select` / `ignore` / per-file-ignores, mypy
  plugin, `dev` group.
- `uv.lock` — regenerated after bandit leaves `dev`.
- `.pre-commit-config.yaml` — new.
- `src/kaleta/services/{import_rule,rule,planned_transaction,saved_report}_service.py`,
  `src/kaleta/views/import_view/page.py` — asserts → raises.
- `src/kaleta/services/event_capture.py`,
  `src/kaleta/views/subscriptions/dialogs.py` — held task references.
- `src/kaleta/observability/ring_buffer.py` — `ClassVar`.
- `src/kaleta/services/backup_service.py`,
  `src/kaleta/services/nbp_rate_service.py` — justified `noqa`.
- 60-odd files — `# noqa` removals, `__all__` sorting, cast cleanups.
- `.claude/agents/security-auditor.md`, `.claude/agents/deps-updater.md`.
- `AGENTS.md`, `CONTRIBUTING.md`.

## Open questions

- mypy on `tests/` and `scripts/`: `uv run mypy tests/ scripts/` has
  never run; the count decides whether it is a follow-up commit on
  this branch or a plan of its own. Fixtures typed `Any` for Playwright
  objects are the expected bulk.
- `pre-push` stage for mypy is a compromise between a slow commit and
  no local type check at all; if it proves annoying, drop the stage
  and rely on CI.

## Implementation notes

- Ruff rules, code fixes, bandit removal, pydantic plugin, pre-commit
  and docs are on `chore/lint-hardening`. `ruff check .` and
  `ruff format --check .` pass on the branch. `uv run mypy src/`,
  `uv lock` and the test suite still have to be run on a machine with
  the dev environment installed before the PR opens — the branch was
  prepared where the package index was not reachable.

## Implementation (filled by plan-archiver)

## Implementation

Landed on 2026-09-24.

| SHA | Author | Date | Message |
|---|---|---|---|
| `69ccc58` | Dawid Adamski | 2026-09-24 | Merge pull request #128 from DawidAdamski/chore/lint-hardening |

**Files changed:**
- .claude/agents/deps-updater.md
- .claude/agents/security-auditor.md
- .pre-commit-config.yaml
- AGENTS.md
- CONTRIBUTING.md
- docs/plans/README.md
- docs/plans/lint-hardening.md
- pyproject.toml
- scripts/bug_reports.py
- scripts/reset_demo.py
- scripts/seed.py
- src/kaleta/db/__init__.py
- src/kaleta/db/types.py
- src/kaleta/main.py
- src/kaleta/models/__init__.py
- src/kaleta/models/transaction.py
- src/kaleta/observability/__init__.py
- src/kaleta/observability/context.py
- src/kaleta/observability/ring_buffer.py
- src/kaleta/schemas/__init__.py
- src/kaleta/schemas/account.py
- src/kaleta/schemas/asset.py
- src/kaleta/schemas/categorisation_rule.py
- src/kaleta/schemas/category.py
- src/kaleta/schemas/import_rule.py
- src/kaleta/schemas/institution.py
- src/kaleta/schemas/planned_transaction.py
- src/kaleta/schemas/reserve_fund.py
- src/kaleta/schemas/salary.py
- src/kaleta/schemas/transaction.py
- src/kaleta/schemas/unplanned_radar.py
- src/kaleta/seeders/base.py
- src/kaleta/services/__init__.py
- src/kaleta/services/auth_stats_service.py
- src/kaleta/services/backup_service.py
- src/kaleta/services/event_capture.py
- src/kaleta/services/import_rule_service.py
- src/kaleta/services/import_service.py
- src/kaleta/services/nbp_rate_service.py
- src/kaleta/services/planned_transaction_service.py
- src/kaleta/services/rule_service.py
- src/kaleta/services/saved_report_service.py
- src/kaleta/services/subscription_service.py
- src/kaleta/views/__init__.py
- src/kaleta/views/auth_common.py
- src/kaleta/views/budget_plan/dialogs.py
- src/kaleta/views/credit.py
- src/kaleta/views/credit_calculator.py
- src/kaleta/views/dashboard_widgets/__init__.py
- src/kaleta/views/dashboard_widgets/balance_card.py
- src/kaleta/views/dashboard_widgets/budget_variance_month.py
- src/kaleta/views/dashboard_widgets/credit_utilization.py
- src/kaleta/views/dashboard_widgets/largest_transactions.py
- src/kaleta/views/dashboard_widgets/month_expenses.py
- src/kaleta/views/dashboard_widgets/month_income.py
- src/kaleta/views/dashboard_widgets/month_net.py
- src/kaleta/views/dashboard_widgets/net_worth.py
- src/kaleta/views/dashboard_widgets/predicted_30d.py
- src/kaleta/views/dashboard_widgets/quick_actions.py
- src/kaleta/views/dashboard_widgets/savings_rate_kpi.py
- src/kaleta/views/dashboard_widgets/top_merchants.py
- src/kaleta/views/dashboard_widgets/total_balance.py
- src/kaleta/views/dashboard_widgets/upcoming_planned.py
- src/kaleta/views/dashboard_widgets/ytd_summary.py
- src/kaleta/views/import_view/page.py
- src/kaleta/views/institutions.py
- src/kaleta/views/reports/page.py
- src/kaleta/views/safety_funds.py
- src/kaleta/views/settings/constants.py
- src/kaleta/views/setup.py
- src/kaleta/views/subscriptions/dialogs.py
- tests/e2e/conftest.py
- tests/e2e/seed_helpers.py
- tests/e2e/test_demo_banner.py
- tests/e2e/test_mfa.py
- tests/e2e/test_planned_transactions.py
- tests/e2e/test_settings_week_debug.py
- tests/e2e/test_transactions.py
- tests/integration/test_example_data.py
- tests/unit/services/test_api_token_service.py
- tests/unit/services/test_import_service.py
- tests/unit/services/test_net_worth_service.py
- uv.lock

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
