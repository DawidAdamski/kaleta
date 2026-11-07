---
plan_id: harness-maintainer-mode
title: Maintainer mode for harness changes, one protected-paths list, terminal exhaustion
area: harness / goal mode
effort: small
status: draft
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Maintainer mode for harness changes, one protected-paths list, terminal exhaustion

## Intent
[ADR-39](../adr/039-measurable-critic-deterministic-judge.md) moves the
review loop to a measurable critic plus a deterministic judge. Every
follow-up plan edits harness files that `.claude/hooks/protect-files.sh`
makes read-only for the agent, which is correct and must stay that way.
This plan adds a controlled way for the *owner* to change the harness, closes
the Bash route around the Edit/Write guard, and fixes two harness defects
seen in `.claude/state/`: exhaustion is not terminal, and the cross-family
reviewer is skipped silently.

## Scope
Covers:
- **One list of protected paths**: `docs/harness/protected-paths.txt`
  (glob per line, `#` comments). Both `protect-files.sh` and `dod-gate.sh`
  read it. Initial content is the paths protected today plus the new
  legislative files:
  `.claude/hooks/**`, `.claude/settings.json`, `.claude/state/**`,
  `.claude/commands/implement-plan.md`, `scripts/verify.sh`,
  `scripts/review_gate.sh`, `scripts/plan_goal.sh`, `scripts/plan_runner.sh`,
  `scripts/harness/**`, `docs/harness/**`, `docs/review-checklist.md`,
  `tests/harness/critic_cases/**`, `docs/plans/archive/**`, and tracked files
  under `alembic/versions/` (existing rule kept).
- **Maintainer mode**: `protect-files.sh` lets an edit through only when
  `KALETA_HARNESS_MAINTAINER=1` is in *the hook's* environment. Hooks
  inherit the environment of the process that launched Claude Code. The
  agent's Bash tool runs in a child shell and cannot change it. Every
  allowed edit is printed to stderr (`protect-files: maintainer edit <path>`).
- **Bash-route veto in the gate**: when the diff against the merge-base
  touches a protected path and the hook's environment lacks
  `KALETA_HARNESS_MAINTAINER=1`, `dod-gate.sh` fails with a reason that names
  the paths. This closes `sed -i` / `cat >` edits that bypass the Edit guard.
- **Plans that change the harness** carry `harness: true` in frontmatter.
  `plan_runner.sh` refuses them (headless never touches the harness).
  `/implement-plan` prints a reminder that the session must be launched as
  `KALETA_HARNESS_MAINTAINER=1 claude`.
- **Terminal exhaustion**: once `.claude/state/result` is `exhausted`, the
  Stop hook exits 0 without judging or counting until `plan_goal.sh start`
  re-arms the plan (which resets `attempts`). A later green run must not
  quietly flip `exhausted` to `done`.
- **Cross review fails loudly**: with `KALETA_CROSS_REVIEW=1`, a missing
  Cursor CLI or unparsable output makes `review_gate.sh` exit non-zero and
  record `verdict: "error"` instead of continuing with the Claude reviewer
  alone.
- Tests under `tests/unit/harness/` that run the shell scripts against a
  temporary git repository (no network, no Claude calls).
- `docs/goal-mode.md`: a "Changing the harness" section (maintainer mode,
  `harness: true`, why harness plans never run headless).

Does **not** cover:
- The audit log, critic, judge or profile (follow-up plans).
- Sandboxing the agent's Bash beyond the gate veto (still a personal repo,
  not a sandbox; see goal-mode.md "What the gate does NOT protect against").

## Acceptance criteria

- `test -f docs/harness/protected-paths.txt`
- `uv run pytest tests/unit/harness/test_protect_files.py -q`
- `uv run pytest tests/unit/harness/test_dod_gate_protected_diff.py -q`
- `uv run pytest tests/unit/harness/test_dod_gate_exhaustion.py -q`
- `uv run pytest tests/unit/harness/test_review_gate_cross_error.py -q`
- `grep -q "harness: true" scripts/plan_runner.sh`
- `grep -q "Changing the harness" docs/goal-mode.md`
- `./scripts/verify.sh`
- `[manual]` In a session launched without the variable, an Edit to
  `scripts/harness/x.py` is refused; with `KALETA_HARNESS_MAINTAINER=1 claude`
  it goes through and is printed as a maintainer edit.

## Touchpoints
- `.claude/hooks/protect-files.sh`, `.claude/hooks/dod-gate.sh`
- `scripts/review_gate.sh`, `scripts/plan_runner.sh`, `scripts/plan_goal.sh`
- `.claude/commands/implement-plan.md` (reminder for `harness: true`)
- `docs/harness/protected-paths.txt` (new)
- `tests/unit/harness/` (new: conftest with a temp-repo fixture, four test files)
- `docs/goal-mode.md`

## Open questions
- *Bootstrap*: this plan edits `protect-files.sh`, which blocks its own
  edit. Default: the owner adds the maintainer-mode check to
  `protect-files.sh` by hand first (about five lines), commits it, then
  runs the rest in a `KALETA_HARNESS_MAINTAINER=1 claude` session.
- *Should the gate itself be armed for harness plans?* Default: yes. The
  gate runs the new code against its own change, the review still applies,
  and the owner reads the diff before merging anyway.
- *Glob matching in bash*: default is `[[ $path == $glob ]]` with
  `shopt -s globstar extglob`; tests pin `**` behaviour.

## Implementation notes
_Filled in as work progresses._
