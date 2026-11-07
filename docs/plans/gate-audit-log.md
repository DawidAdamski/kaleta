---
plan_id: gate-audit-log
title: Append-only, tamper-evident run log for every gate and review run
area: harness / goal mode
effort: medium
status: draft
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Append-only, tamper-evident run log for every gate and review run

## Intent
Nothing in the loop is measured today: `.claude/state/review-verdict.json`
is overwritten on every run and git-ignored, and `logs/plans/` holds one
aborted file. Without a record there is no reviewer miss rate, no cost per
plan, no replay of a decision, and no data to calibrate a critic on
([ADR-39](../adr/039-measurable-critic-deterministic-judge.md), principle 5).
This plan records every judgement as data. It does not change any decision.

## Scope
Covers:
- `scripts/harness/gate_log.py` (stdlib only), with subcommands:
  - `append <plan_id> --kind gate|review --json <file|->`: adds one line to
    `docs/harness/runs/<plan_id>.jsonl`;
  - `verify [<plan_id>]`: checks the hash chain (each line stores `prev`,
    the sha256 of the previous line, plus its own `sha`). Any edit, deletion
    or reordering fails;
  - `report [--since DATE]`: per plan (attempts, outcome, review runs,
    critic cost in USD, wall time) and in total (done / exhausted / blocked
    / escalated rates, median attempts, cost per merged plan).
- **Gate record** (written by `dod-gate.sh` on every run, dry runs marked
  `dry: true`): `ts`, `plan_id`, plan file sha, checklist sha,
  `protected-paths.txt` sha, branch, base, `diff_hash`, changed paths with
  added and removed line counts, attempt and max, each check as
  `{name, ok, seconds, tail}` (hygiene, green-washing, every acceptance
  criterion, verify.sh, review freshness), the outcome
  (`block | done | exhausted`), the reasons, and whether maintainer mode
  was on.
- **Review record** (written by `review_gate.sh`): `ts`, `diff_hash`,
  reviewer ids and models, verdict, findings, `total_cost_usd` and turns
  taken from the `claude -p` JSON (and the Cursor reviewer when used),
  parse failures included as `verdict: "error"`.
- `docs/harness/runs/` is committed with the plan's PR. It is written by the
  hooks and scripts, never by the agent's Edit/Write (it sits under the
  protected `docs/harness/**`). It is excluded from `diff_hash` in both
  `dod-gate.sh` and `review_gate.sh`, so writing a log line does not make a
  review stale. It is also exempt from the protected-path diff veto, but
  `gate_log.py verify` runs in the gate and in CI, so an edit made through
  Bash still breaks the chain.
- CI: `ci.yml` runs `uv run python scripts/harness/gate_log.py verify` on
  pull requests.
- `docs/goal-mode.md`: a "Run log" section with the format and the
  `report` command.

Does **not** cover:
- Changing what the gate decides (that is `judge-profile-and-autonomy`).
- Shipping logs to Loki/Grafana (goal-mode.md roadmap; later).
- Back-filling logs for already-archived plans.

## Acceptance criteria

- `uv run pytest tests/unit/harness/test_gate_log.py -q`
- `uv run pytest tests/unit/harness/test_dod_gate_writes_log.py -q`
- `uv run python scripts/harness/gate_log.py verify`
- `uv run python scripts/harness/gate_log.py report --help`
- `grep -q "gate_log.py verify" .github/workflows/ci.yml`
- `grep -q "Run log" docs/goal-mode.md`
- `./scripts/verify.sh`

## Touchpoints
- `scripts/harness/gate_log.py` (new), `scripts/harness/__init__.py` if needed for tests
- `.claude/hooks/dod-gate.sh`, `scripts/review_gate.sh`, `scripts/plan_runner.sh` (summary line reads the log)
- `docs/harness/runs/` (new, committed)
- `.github/workflows/ci.yml`
- `tests/unit/harness/test_gate_log.py`, `test_dod_gate_writes_log.py`
- `docs/goal-mode.md`

## Open questions
- *Where the log lives.* Default: committed under `docs/harness/runs/` with
  the plan's PR, so the history survives worktrees and is reviewable.
  Alternative considered: a git-ignored `logs/gate/`, which is lost with the
  worktree and invisible to CI.
- *Size.* `tail` fields keep at most 40 lines per failing check. A plan
  with six attempts should stay well under 200 KB.
- *Clock / ordering.* The chain hash gives the order; `ts` is informational.

## Implementation notes
_Filled in as work progresses._
