---
plan_id: critic-calibration-set
title: Calibration set from the repo's own history, seeded defects and counterfactual pairs; per-question critic metrics
area: harness / review
effort: large
status: in-progress
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Calibration set from the repo's own history, seeded defects and counterfactual pairs; per-question critic metrics

## Intent
A threshold means something only when the probability under it is honest:
"0.67" has to mean the critic is right about two times in three. Following
the talk's basal experiment (accuracy, ECE, Brier, counterfactual flip on a
calibration split, with a test split used once), this plan measures the
critic from `critic-narrow-questions` on Kaleta's own history. The output is
a calibration report the judge reads
([ADR-39](../adr/039-measurable-critic-deterministic-judge.md), principle 5).
KPI number one is the critic's **miss rate in the autonomy zone**: true
violations it lets through.

## Scope
Covers:
- **Case builder** `scripts/harness/seed_defects.py`:
  - **clean cases**: for archived plans whose PR merge commit is known,
    rebuild `(base, merged diff, plan file at that commit)` in a temporary
    worktree. A case is labelled clean only if no `fix` commit touched the
    same files within 30 days after merge. The label is a heuristic, and the
    report says so;
  - **seeded defects**: mutation operators per question, applied to a
    clean case so that exactly one fact changes (a counterfactual pair):
    - `M-SCOPE`: add an edit to an unrelated module;
    - `M-SERVICE-TEST`: delete the test that covers a changed service
      function, or strip its assertions;
    - `M-VIEW-LOGIC`: inline a service query into the view that calls it
      (template-based, only for plans that touched both);
    - `M-TENANT`: swap a family session for a public-registry session in one
      new query;
    - `M-KAL`: remove the new `KAL-` scenario and its `Covers:` line;
    - `M-NOTES`: add a sentence to Implementation notes that claims a test
      or decision that is not in the diff;
    - `M-MIGRATION`: remove the migration that goes with a model change.
    Every case stores gold answers for all applicable questions: the mutated
    question is `yes`, the rest copy the clean case;
  - **split by plan**: a plan and all its variants are always in one split,
    so no leakage. Default is 70% `calib`, 30% `test`. The test split's case
    ids are hashed into `docs/harness/calibration/test-split.sha256`.
  - Cases are stored as small patch bundles under
    `tests/harness/critic_cases/` (protected: the executor must not edit the
    exam). They are not collected by pytest.
- **Runner** `scripts/harness/calibrate_critic.py --split calib|test`:
  - runs `critic.py` (real model, *k* from the profile) on every case,
    with `--budget-usd` (required) and `--max-cases`, and resumes from
    partial results;
  - the test split runs **once per critic hash**. A second run needs
    `--force --reason "<text>"` and the reason is logged;
  - **metrics per question**: n, accuracy, miss rate (FN / violations),
    false-alarm rate, Brier score, a reliability table at the reachable
    levels for k=3 (0, ⅓, ⅔, 1) with ECE, counterfactual flip rate (share
    of pairs where the answer moved the right way), invalid-evidence rate,
    and 95% Wilson intervals for the rates. Plus totals, cost, and the
    critic hash;
  - writes `docs/harness/calibration/<critic_hash>-<split>.json` and `.md`.
- **Judge wiring**: the profile's `[calibration] report` points at a test
  report. A question is *calibrated* when the report's critic hash equals
  the current one and the upper bound of its miss rate is at or below
  `[calibration] miss_rate_target` (default 0.10, the talk's α). Anything
  else keeps the cap at B (already implemented in
  `judge-profile-and-autonomy`).
- `docs/goal-mode.md` "Calibrating the critic": how to build cases, run the
  calib split, tune thresholds, run the test split once, sign the profile.

Does **not** cover:
- Turning on auto-merge. The report is the evidence; the decision stays the
  owner's (`allow_auto_merge`).
- Running calibration in `verify.sh` or on every PR (it costs real money).
- Training a local critic model on the cases (future; the set is designed
  to be reusable as training data).

## Acceptance criteria

- `uv run pytest tests/unit/harness/test_calibration_metrics.py -q`
- `uv run pytest tests/unit/harness/test_seed_defects.py -q`
- `uv run pytest tests/unit/harness/test_split_no_leakage.py -q`
- `uv run python scripts/harness/seed_defects.py --dry-run --max-plans 3`
- `uv run python scripts/harness/calibrate_critic.py --split calib --dry-run --budget-usd 1`
- `./scripts/verify.sh`
- `[manual]` First calib report committed under `docs/harness/calibration/`,
  thresholds in `profile.toml` updated from it, profile re-signed.
- `[manual]` Test split run once; its report is the one `profile.toml`
  points at.

## Touchpoints
- `scripts/harness/seed_defects.py`, `scripts/harness/calibrate_critic.py` (new)
- `tests/harness/critic_cases/` (new, protected), `docs/harness/calibration/` (new)
- `docs/harness/profile.toml` (`[calibration]` section)
- `tests/unit/harness/` (metrics on synthetic data, mutation operators on a fixture repo, split leakage)
- `docs/goal-mode.md`

## Open questions
- *Size and budget.* 193 plans are archived, but not all have a
  recoverable merge diff and a mutation that fits. Default first pass:
  about 30 plans, which with 3–4 variants each is about 100 cases, × k=3,
  so about 300 critic runs on `sonnet`. At recent review costs that is a few
  hundred USD. Start with `--budget-usd 50` on the calib split and grow.
  The intervals will be wide at this n, and the report shows them.
- *Label noise in "clean" cases.* The 30-day no-fix heuristic misses latent
  bugs. Default: accept it and report false alarms on clean cases
  separately. Mutant recall is the trustworthy number.
- *Questions without a mutation operator* (`Q-AUTH-SURFACE`,
  `Q-REGRESSION-TEST`, `Q-SECRET-DATA`): stay uncalibrated in the first
  report, so changes hitting them stay capped. Operators are a follow-up
  chore.

## Implementation notes

- **Size (open question, default taken):** `seed_defects.py --max-plans 30`
  built 30 plans → **121 cases** (93 `calib`, 28 `test`). Mutants per operator:
  M-SCOPE 30, M-NOTES 30, M-KAL 20, M-VIEW-LOGIC 4, M-TENANT 3, M-MIGRATION 3,
  M-SERVICE-TEST 1. 85 of the archived plans have no recoverable merge (merged
  from a branch whose name does not end in the plan id, or before the
  `plan/<id>` convention). Newest plans first: today's questions fit them best.
- **Questions this set cannot calibrate yet.** With 1–4 mutants, Q-SERVICE-TEST,
  Q-TENANT-ISOLATION, Q-MIGRATION and Q-VIEW-LOGIC will have miss-rate upper
  bounds far above 0.10 whatever the critic does; like the three questions
  without an operator, they stay capped. Growing them needs more plans
  (`--max-plans`) or looser operators — a follow-up, not this plan.
- **Merge discovery.** A plan's case is the newest first-parent merge
  `Merge pull request #N from <owner>/<…>/<plan_id>`; `docs/archive-<id>`
  merges are skipped (the first dry run picked those up — their diff is the
  plan file moving to the archive). base = merge-base of the PR, head = its
  last commit.
- **Clean label narrowed to Python sources.** "Same files" first meant every
  file of the PR; shared files (`docs/bdd.md`, the locale JSON, `chores.md`)
  are touched by nearly every later fix, and 39 of the newest 40 plans were
  rejected. Now only the PR's `src/**/*.py` count. The report's `label_note`
  says the label is a heuristic; mutant recall is the trustworthy number.
- **Operators keep it to one fact.** M-SCOPE edits a module docstring outside
  `services/ views/ api/ models/ auth/ db/ crypto/` (a change there would make
  another question true as well). M-SERVICE-TEST only fires for a *new* service
  function whose every test the PR wrote, and backs off when deleting them
  would leave a `KAL-` id with no `Covers:` (that would flip Q-KAL-SCENARIO).
  M-VIEW-LOGIC inserts a template helper (query + money rounding) into a view
  the PR changed. Gold for the non-target questions of a mutant copies the
  clean case (`no`), as the plan says; where a mutation could arguably touch
  another question (an unused helper looks like scope creep), that is label
  noise the report does not hide.
- **Replaying an old case.** The runner makes a temporary worktree at the
  case's base, lays today's `critic-questions.toml`, `profile.toml`,
  `review-checklist.md`, `.claude/settings.json` and `.claude/hooks/` over it
  as one commit, applies the PR diff and the mutation (both `--index`), and
  runs today's `critic.py` with the new **`--base <overlay commit>`** option
  (the gate never passes it; `profile_settings` reads the profile at that
  base). A PR that changed one of those overlay files is skipped when the
  cases are built. The worktree reuses this checkout's `.venv` without syncing
  (`UV_PROJECT_ENVIRONMENT`, `UV_NO_SYNC`) with the case's `src` first on
  `PYTHONPATH`, so a sample's `uv run pytest` tests the case's code.
- **One run, up to two critic hashes.** The critic adds a local-model sample
  on its own where the profile requires one (high risk), and the hash covers
  the model list — the smoke run on `gifts-mark-bought--m-tenant` came back
  `613e8b9ab733ffd9`, not `36ef5368e55e44a3`. Each case result records its
  real hash; results go to `docs/harness/calibration/<split>.cases.jsonl` and a
  report is written per hash. `[calibration] report` may therefore be a list;
  `gate.calibration` takes the report whose hash is the reviewing critic's.
- **What the gate accepts.** Only a report with `split = "test"` and
  `complete = true` (every test case ran) counts — thresholds are tuned on the
  calib split. "Runs once" means one complete run: a test run cut short by the
  budget resumes; after a complete one, `--force --reason` is required and the
  reason is logged in the report and `forced-runs.log`.
- **Metric definitions.** Miss = a violation whose p is under `uncertain`
  (between `uncertain` and `block` the judge escalates, so it is not let
  through); a violation with no valid sample is a miss too. False alarm = a
  clean answer with p ≥ `block`. Accuracy uses p ≥ `block`. Totals sum the
  per-question counts, because thresholds differ per question.
- **Smoke test without a model:** `run_case` on a real case with
  `KALETA_CRITIC_FAKE` built the worktree, applied diff and patch, ran the
  critic and cleaned up. No real calibration has run: that is the owner's
  manual criterion and costs money (estimate ≈ 0.90 USD per case at k = 3:
  ≈ 85 USD for the calib split, ≈ 25 USD for the test split).
- **`profile.toml` is not edited here.** Pointing `[calibration] report` at a
  test report, retuning thresholds and re-signing are the owner's (manual
  criteria). `docs/goal-mode.md` "Calibrating the critic" has the steps.
- **Gate warning "New '# type: ignore'"** points at
  `tests/harness/critic_cases/gifts-mark-bought--m-service-test/mutation.patch`:
  a *removed* test line stored as patch data, not code anyone runs or types.
