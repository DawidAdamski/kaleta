# Goal mode — implementing plans with an agent that cannot stop early

Goal mode turns a plan in `docs/plans/` into a completion condition. The
agent works until a **deterministic judge** says the plan is done; it
cannot declare victory by itself. The judge is a Claude Code `Stop`
hook, but every check it runs is a plain script, so the same gate works
from Cursor or a headless runner.

```
/implement-plan <plan_id>          (interactive, Claude Code)
scripts/plan_runner.sh [...]       (headless, one worktree + branch per plan)
        │
        ▼
scripts/plan_goal.sh start ──► .claude/state/active-plan   (arms the gate)
        │
        ▼
  implementer works ──► wants to finish ──► .claude/hooks/dod-gate.sh
                                              │  plan hygiene (status, Implementation notes)
                                              │  green-washing check (skip/xfail/ignore_imports)
                                              │  plan's executable acceptance criteria
                                              │  ./scripts/verify.sh [--e2e]
                                              │  fresh review verdict (scripts/review_gate.sh)
                                              ▼
                              block + reason ──► implementer fixes, tries again (≤ max attempts)
                              pass            ──► session ends, PR is opened by a human or --pr
```

## Files

| File | Role |
|---|---|
| `.claude/settings.json` | wires the two hooks below (project-level, committed) |
| `.claude/hooks/dod-gate.sh` | **Stop hook** — the judge; active only while a plan is armed |
| `.claude/hooks/protect-files.sh` | **PreToolUse hook** — agent cannot edit the harness, archived plans, applied migrations |
| `.claude/commands/implement-plan.md` | `/implement-plan <plan_id>` — the interactive entry point; also the prompt used by the runner |
| `.claude/agents/reviewer.md` | interactive, explainable review (same rubric as CI) |
| `scripts/plan_goal.sh` | `start / status / block / finish` — goal state in `.claude/state/` |
| `scripts/review_gate.sh` | independent headless reviewer (+ optional Cursor CLI second opinion); writes the verdict the gate requires |
| `scripts/plan_runner.sh` | headless queue consumer over `docs/plans/` |
| `scripts/plan_archive.sh` | archive a merged plan (used by `.github/workflows/plan-archive.yml`) |
| `.claude/state/` | runtime state, git-ignored: `active-plan`, `attempts`, `result`, `review-verdict.json`, `verify-last.log` |

## Interactive run (start here)

```bash
uv sync --group dev            # once; jq must be installed too (brew install jq)
claude                         # in the repo
> /implement-plan transactions-notes-field
```

No need to remember plan ids: plain `/implement-plan` lists the draft
plans, recommends one and asks which to take.

What happens: the command arms the gate, creates `plan/transactions-notes-field`
from `main`, flips the plan to `in-progress`, and the agent works. Each
time it tries to finish, the gate runs and either lets it stop (all
green + review approved) or feeds the failures back. You watch every
turn; `Esc` interrupts as usual. When it ends, the report contains the
`gh pr create` command — pushing and opening the PR stays a human step
in interactive mode.

Optional belt-and-braces: after `/implement-plan …` you can also set
`/goal plan <plan_id> implemented, gate passed, or stop after 40 turns`
— the model-judged goal adds a turn cap on top of the script-judged gate.

Useful while it runs (from another terminal):

```bash
scripts/plan_goal.sh list draft  # which plans are waiting (id / status / effort / area)
scripts/plan_goal.sh status      # attempts, result, review verdict
scripts/review_gate.sh           # run the independent review yourself
scripts/plan_goal.sh block "needs a design decision on X"   # let it stop
scripts/plan_goal.sh finish      # disarm the gate
```

## Headless run (later — the queue)

```bash
scripts/plan_runner.sh --dry-run                       # what would run: draft + small by default
scripts/plan_runner.sh transactions-notes-field        # one plan, no push
scripts/plan_runner.sh --effort small --max 3 --pr     # three small drafts, open PRs
scripts/plan_runner.sh --status draft --effort medium --max-turns 120 --max-attempts 8
```

Each plan gets its own git worktree under `../kaleta-worktrees/<plan_id>`
and a fresh `claude -p` session (`--permission-mode dontAsk` + an explicit
`--allowedTools` list — anything outside it is refused, never asked).
Results land in `logs/plans/<plan_id>.json`; the summary at the end says
`done`, `exhausted` (gate attempts used up — inspect the worktree),
`blocked` (agent asked for a human decision, reason in
`.claude/state/blocked-reason`) or `no-result`.

The runner never merges. With `--pr` it pushes and opens a PR whose body
carries the verify.sh tail and the review verdict; the CI reviewer
(`.github/workflows/pr-review.yml`) then reviews it a second time, and you merge.

## After merge: archiving is automatic

Merging a `plan/<plan_id>` PR triggers `.github/workflows/plan-archive.yml`.
It runs `scripts/plan_archive.sh <plan_id> --sha <merge> --pr <N> --fast`
(the deterministic twin of the `plan-archiver` subagent: `## Implementation`
section, `status: archived`, move to `archive/`, README index row) and
opens a `docs/archive-<plan_id>` PR for you to merge. By hand, e.g. for
plans merged before this workflow existed:

```bash
scripts/plan_archive.sh transactions-notes-field --pr 69          # re-runs acceptance criteria
scripts/plan_archive.sh transactions-notes-field --sha ce08435 --fast
```

The gate disarms itself once the plan file lands in `archive/` (or when
the result is `done` and you are no longer on the plan branch), so a
forgotten `plan_goal.sh finish` cannot judge an unrelated session.

## The reviewer(s)

`scripts/review_gate.sh` spawns a read-only `claude -p` in a fresh context
with `docs/review-checklist.md` as rubric and the plan as scope contract —
the same instructions as the CI reviewer, so a local approve predicts the
PR review. The verdict is bound to a hash of the diff; any further edit
makes it stale and the gate demands a re-review.

Second opinion from another model family (hybrid setup with Cursor):

```bash
export KALETA_CROSS_REVIEW=1
export KALETA_CROSS_REVIEW_MODEL=gpt-5      # any model the Cursor CLI can use
scripts/review_gate.sh
```

Requires the Cursor CLI (`curl https://cursor.com/install -fsS | bash`,
binary `agent`, older installs `cursor-agent`). Both reviewers must
approve. The CLI flags (`-p`, `--model`, `--output-format`) are checked
against `agent --help` if the call fails — the script logs raw output to
`.claude/state/review-cross-raw.txt`.

Model choices: `KALETA_REVIEW_MODEL` (default `sonnet`) for the Claude
reviewer; `--model` on the runner for the implementer.

## What the gate does NOT protect against

- **A plan with prose-only acceptance criteria.** Older plans (e.g.
  `transactions-notes-field`) list criteria as sentences. The gate warns
  and relies on verify.sh + the reviewer. Rewrite criteria as backtick
  commands (`docs/plans/README.md`) before running a plan headless.
- **Forged verdicts.** The agent may run Bash; a determined model could
  write `.claude/state/review-verdict.json` by hand. The Edit/Write
  tools are blocked on that path and the prompt forbids it, but this is a
  personal repo, not a sandbox. In CI use `--bare` and a separate step.
- **Semantic drift.** Everything green, reviewer approved, behaviour
  still not what you meant. That is why merge stays human.

## Cursor: the same gate, a different loop

Nothing here depends on Claude Code to *judge* a plan — the judge is
`scripts/plan_goal.sh check` (plan hygiene, acceptance criteria,
`verify.sh`, green-washing, review verdict). Claude Code only adds the
`Stop` hook that calls it automatically and blocks the session.

Cursor has no equivalent "block the stop and feed the reason back"
hook, so the loop is Ralph-style instead — same judge, driven from
outside:

- **Interactive in Cursor**: arm the plan (`scripts/plan_goal.sh start <id>`),
  tell the agent to implement the plan per AGENTS.md and to run
  `scripts/plan_goal.sh check` before it stops, fixing whatever it
  prints, until it passes. The rules in `.cursor/rules/kaleta.mdc` still
  apply (no commits without asking).
- **Headless with the Cursor CLI**: `scripts/plan_runner.sh --engine cursor --model <id> <plan_id>`
  runs `agent -p` up to `--max-attempts` rounds, judges with
  `plan_goal.sh check` after each, and feeds the verdict back. Any model
  the Cursor CLI exposes works, Anthropic ones included.
- **Cursor as second reviewer**: `KALETA_CROSS_REVIEW=1` (see above).

Trade-off in one line: Cursor gives you one subscription and every model
family; Claude Code gives you the native Stop hook (no external loop),
`/goal`, subagents with their own context, and the Agent SDK for the
Tekton stage. The gate is shared, so you can switch engines per plan.

## Roadmap for this harness

- Tekton on k3d: `plan_runner.sh` becomes a `Task` (clone → implement →
  review → pr) with the same scripts inside a runner image; Flux keeps
  the pipeline manifests in sync. The scripts already avoid interactive
  git and take everything from env/args for that reason.
- OpenRouter as a second reviewer backend when the Cursor CLI is not
  available on the runner.
- Ship `logs/plans/*.json` (turns, cost, result) to Loki/Grafana for a
  per-plan cost and success dashboard.
