---
plan_id: judge-profile-and-autonomy
title: Deterministic judge over an owner-signed profile, autonomy chosen per change, escalation as an outcome
area: harness / goal mode
effort: large
status: in-progress
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Deterministic judge over an owner-signed profile, autonomy chosen per change, escalation as an outcome

## Intent
The gate today is an AND of checks, and every plan ends in the same mode: the
gate passes and the owner merges. A change to `alembic/` and auth is treated
like a change to locale files. Uncertainty never reaches the owner; only
exhaustion does. Per [ADR-39](../adr/039-measurable-critic-deterministic-judge.md)
the decision becomes a pure, replayable function of the evidence and of a
profile that only the owner writes. It picks the autonomy mode for *this*
change and can hand the change to the owner with reasons.

## Scope
Covers:
- **Profile** `docs/harness/profile.toml` (protected; read with stdlib
  `tomllib`):
  - `[meta]`: `version`, `owner`, `signed` (date). The judge refuses a
    profile without them;
  - `[vetoes]`: the green-washing patterns now hard-coded in `dod-gate.sh`
    (skip/xfail, `ignore_imports`), moved here as regexes on added lines;
    the protected-path rule from `harness-maintainer-mode`; and
    `Q-SECRET-DATA` with `p_violation > 0` (any sample with valid evidence)
    means mode D;
  - `[risk_classes]`: path globs. Defaults:
    - `high`: `alembic/**`, `alembic_public/**`, `src/kaleta/auth/**`,
      `src/kaleta/crypto/**`, `src/kaleta/db/**`, tenancy and household
      services, `deploy/**`, `.github/**`, `Containerfile*`;
    - `low`: only `docs/**` (except `docs/harness/**`),
      `src/kaleta/i18n/locales/**`, `tests/**`;
    - `medium`: everything else.
    The class of a change is its highest-risk path. A plan with no
    executable acceptance criteria is at least `high`;
  - `[thresholds]`: per question `block` (default 0.67) and `uncertain`
    (default 0.34). Unlisted questions use the defaults;
  - `[autonomy]`: per class `low = "A"`, `medium = "B"`, `high = "C"`;
    `allow_auto_merge = false`; `critic_samples` per class (default 3 each);
    `cross_family_required = ["high"]`;
  - `[calibration]`: path to the calibration report the thresholds were set
    against (empty until `critic-calibration-set`).
- **Judge** `scripts/harness/judge.py`:
  `decide(inputs: GateInputs, profile: Profile) -> Decision`, pure (no I/O,
  no clock, no randomness).
  - `GateInputs`: check results, critic questions (`p_violation`,
    `k_valid`, evidence), changed paths, plan metadata (executable criteria
    count, `harness` flag), maintainer flag, prior review rounds for this
    diff lineage;
  - order: (1) vetoes → `escalate`, mode D; (2) failed checks → `block`;
    (3) any question `p >= block` → `block` with evidence;
    (4) `uncertain <= p < block` → `block` once with "strengthen evidence
    for Q-X" (test, notes, or a narrower change); if it is still uncertain
    after the next review round → `escalate` with the question and the
    samples' notes; (5) otherwise `done`, with the mode from the risk class,
    capped at B when the change hits an uncalibrated question or there is no
    calibration report, and raised to C when a required cross-family sample
    is missing;
  - `Decision`: `outcome` (`done | block | escalate`), `mode` (`A`–`D`),
    `reasons` (each pointing at the input that caused it), and
    `would_change` (what would move the decision, e.g. "Q-SERVICE-TEST at
    0.33 → no test cited for `TenantService.resume`; a test covering it
    lifts the cap").
  - CLI: `judge.py decide --inputs <json>` and
    `judge.py replay docs/harness/runs/<plan>.jsonl`. The second recomputes
    every recorded decision and fails on any difference.
- **`dod-gate.sh`** collects `GateInputs` into JSON, calls `judge.py`, and
  acts on the result:
  - `block` → as today (feed the reasons back, count the attempt);
  - `done` → `result=done`, `mode` saved to `.claude/state/mode`;
  - `escalate` → `result=escalated`, stop allowed, no further attempts.
  It always writes `.claude/state/decision.md` and the gate record (now
  including the full `GateInputs` and `Decision`, so replay works).
- **Decision note** `decision.md`, in plain English for the owner: what the
  change does, the chosen mode and why not a freer one, what the owner will
  see, what would change the decision, and the numbers. `plan_runner.sh --pr`
  puts it at the top of the PR body and adds the labels `autonomy:<mode>`
  and, for C, `needs-owner-review`. `/implement-plan` step 8 prints it.
- `plan_goal.sh status` shows the mode and the last decision. `plan_runner.sh`
  reports `escalated` as its own result (next to done, exhausted, blocked).
- The critic sample count and the cross-family requirement come from the
  profile (`critic.py` reads it).

Does **not** cover:
- Merging anything automatically. Mode A is a label while
  `allow_auto_merge = false`; enabling it is a separate owner decision
  backed by a calibration report.
- Producing the calibration report (`critic-calibration-set`). Until it
  exists every change is capped at B, which is today's behaviour, so
  nothing regresses.
- MCDA ranking (rejected in ADR-39).

## Acceptance criteria

- `test -f docs/harness/profile.toml`
- `uv run python scripts/harness/judge.py check-profile`
- `uv run pytest scripts/harness/tests/test_judge.py -q`
- `uv run pytest scripts/harness/tests/test_gate_judge.py -q`
- `uv run python -c "import tomllib; p=tomllib.load(open('docs/harness/profile.toml','rb')); assert p['autonomy']['allow_auto_merge'] is False"`
- `grep -q "escalated" scripts/plan_runner.sh`
- `./scripts/verify.sh`
- `[manual]` A plan touching `src/kaleta/auth/` ends in mode C with
  `decision.md` naming the risk class. A docs-only plan ends in mode B
  ("uncalibrated cap") and says so.

## Touchpoints
- `docs/harness/profile.toml` (new), `docs/harness/README.md`
- `scripts/harness/judge.py`, `scripts/harness/planfile.py` (new)
- `scripts/harness/gate.py` (collects evidence, pools critic runs, calls the judge), `critic.py` (risk class, samples and cross-family rule from the profile), `protected.py` (rules from the merge-base)
- `scripts/plan_goal.sh`, `scripts/plan_runner.sh`, `.claude/commands/implement-plan.md`
- `.github/workflows/ci.yml` (profile check, replay)
- `scripts/harness/tests/test_judge.py`, `test_gate_judge.py`
- `docs/goal-mode.md` (roles, diagram, judge and profile), `docs/review-checklist.md` (pointer)

## Open questions
- *Thresholds before calibration.* Default `block = 0.67`, `uncertain = 0.34`
  (2 of 3, 1 of 3), recorded in the profile as provisional.
- *How many "strengthen evidence" rounds.* Default one, then escalate.
  Stored in the profile as `uncertain_rounds = 1`.
- *Risk class of mixed changes.* Default: the highest class wins. A plan
  that mixes docs and auth is high risk.
- *Who can raise a class's mode?* Only the profile, so only the owner.
  The implementer cannot argue a mode up.

## Implementation notes
- **The law comes from `main`.** A test caught that the gate read the
  profile from the working tree, which the implementer can change through
  Bash. The gate now reads `profile.toml` and `protected-paths.txt` from the
  merge-base (`git show <base>:…`), and every gate record says where the
  profile came from (`profile_source`). Maintainer sessions read the working
  tree. Touching the profile is still a protected-path veto.
- **Pooling instead of re-rolling.** Re-running the critic on an unchanged
  diff could have produced a lucky draw. The gate pools every successful
  critic run with the same diff hash and critic hash from the run log
  (`runs_pooled`), so extra runs only sharpen the estimate.
- **Vetoes end the session.** A protected path changed outside maintainer
  mode, a secret pattern on an added line, or the critic reporting secret
  data escalate in mode D instead of blocking: an implementer that touched
  the judge does not get more attempts. The plan-1 tests were updated to
  that.
- **Thresholds 0.66 / 0.33** (see `critic-narrow-questions`): 2 of 3 and
  1 of 3 with k=3. Tenant isolation and auth surface block on a single valid
  sample.
- **No valid answer** for a question (every sample's evidence invalid)
  blocks with "run the critic again" (`critic.no_answer.*`) rather than
  counting as clean.
- **Cross-family required for high risk** (`cross_family_required =
  ["high"]`): without the Cursor CLI, a high-risk plan ends escalated with
  the reason, which is the owner's call by design. Remove `"high"` from the
  list in the profile to relax it.
- **Dry runs** (`plan_goal.sh check`) report "would be DONE in mode X" or
  "Would ESCALATE" without touching `result`.
- **Labels.** `plan_runner.sh --pr` creates `autonomy:<mode>` (and
  `needs-owner-review` for C) with `gh label create --force` and adds them
  after the PR exists, so a missing label never fails the PR.
- **Defaults taken:** `uncertain_rounds = 1`, highest class wins for mixed
  changes, only the profile can change a class's mode.
