---
plan_id: judge-profile-and-autonomy
title: Deterministic judge over an owner-signed profile, autonomy chosen per change, escalation as an outcome
area: harness / goal mode
effort: large
status: draft
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
- `uv run pytest tests/unit/harness/test_judge_decide.py -q`
- `uv run pytest tests/unit/harness/test_judge_profile.py -q`
- `uv run pytest tests/unit/harness/test_judge_replay.py -q`
- `uv run pytest tests/unit/harness/test_dod_gate_judge.py -q`
- `uv run python scripts/harness/judge.py replay tests/unit/harness/fixtures/runs/sample.jsonl`
- `uv run python -c "import tomllib; p=tomllib.load(open('docs/harness/profile.toml','rb')); assert p['autonomy']['allow_auto_merge'] is False"`
- `grep -q "escalated" scripts/plan_runner.sh`
- `./scripts/verify.sh`
- `[manual]` A plan touching `src/kaleta/auth/` ends in mode C with
  `decision.md` naming the risk class. A docs-only plan ends in mode B
  ("uncalibrated cap") and says so.

## Touchpoints
- `docs/harness/profile.toml` (new)
- `scripts/harness/judge.py` (new), `scripts/harness/critic.py` (reads the profile)
- `.claude/hooks/dod-gate.sh`, `scripts/plan_goal.sh`, `scripts/plan_runner.sh`
- `.claude/commands/implement-plan.md` (step 8: print `decision.md`)
- `tests/unit/harness/` (decide is table-driven, one case per branch above; replay fixture)
- `docs/goal-mode.md` (judge, profile, modes), `docs/review-checklist.md` (points at the question set)

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
_Filled in as work progresses._
