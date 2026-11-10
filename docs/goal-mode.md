# Goal mode — implementing plans with an agent that cannot stop early

Goal mode turns a plan in `docs/plans/` into a completion condition. The
agent works until a **deterministic judge** says the plan is done; it
cannot declare victory by itself. The judge is a Claude Code `Stop`
hook, but every check it runs is a plain script, so the same gate works
from a headless runner or any agent CLI driven in a loop.

The roles follow a separation of powers
([ADR-39](adr/039-measurable-critic-deterministic-judge.md)): the
**implementer** proposes a diff and never judges it; the **critic** answers
narrow questions with evidence and a sampled probability, never a verdict;
the **judge** is plain code applying the owner's profile; the **owner**
writes the profile, the questions and the checklist, and merges.

```
/implement-plan <plan_id>          (interactive, Claude Code)
scripts/plan_runner.sh [...]       (headless, one worktree + branch per plan)
        │
        ▼
scripts/plan_goal.sh start ──► .claude/state/active-plan   (arms the gate)
        │
        ▼
  implementer works ──► wants to finish ──► .claude/hooks/dod-gate.sh → scripts/harness/gate.py
                                              │  protected paths, secrets          (vetoes)
                                              │  plan hygiene, acceptance criteria, verify.sh [--e2e]
                                              │  green-washing patterns            (profile)
                                              │  critic's p per question, pooled   (scripts/review_gate.sh)
                                              ▼
                                   judge.decide(evidence, profile from main)
                                              │
                    block + reasons ──► implementer fixes, tries again (≤ max attempts)
                    done, mode A–C  ──► session ends; decision.md; PR by a human or --pr
                    escalate (C/D)  ──► session ends; the owner decides
```

## Files

| File | Role |
|---|---|
| `.claude/settings.json` | wires the two hooks below (project-level, committed) |
| `.claude/hooks/dod-gate.sh` | **Stop hook** — active only while a plan is armed; runs `scripts/harness/gate.py` |
| `scripts/harness/gate.py` | the judge: collects the evidence, decides, writes the run log |
| `scripts/harness/gate_log.py` | append-only, hash-chained run log in `docs/harness/runs/` |
| `.claude/hooks/protect-files.sh` | **PreToolUse hook** — agent cannot edit the paths in `docs/harness/protected-paths.txt` (harness, owner's rules, archived plans, applied migrations) unless the session runs in maintainer mode |
| `docs/harness/protected-paths.txt` | the one list of protected paths, read by the hook and by the gate |
| `.claude/commands/implement-plan.md` | `/implement-plan <plan_id>` — the interactive entry point; also the prompt used by the runner |
| `.claude/agents/reviewer.md` | interactive critic: the same questions, with explanations |
| `scripts/plan_goal.sh` | `start / status / block / finish` — goal state in `.claude/state/` |
| `scripts/review_gate.sh` → `scripts/harness/critic.py` | the critic: k samples answer the narrow questions in `docs/harness/critic-questions.toml`; writes `critic.json` (+ a local-model sample from another family) |
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

## The critic

The critic is an expert witness, not a judge
([ADR-39](adr/039-measurable-critic-deterministic-judge.md)).
`scripts/review_gate.sh` runs `scripts/harness/critic.py`:

1. picks the questions from `docs/harness/critic-questions.toml` whose
   `applies_to` globs match the changed paths (scope, service tests, view
   logic, tenant isolation, auth surface, migrations, `KAL-` scenarios,
   truthful notes, secrets);
2. runs **k samples** (default 3) — fresh, read-only `claude -p` contexts,
   each answering every question `yes | no | na`;
3. **checks the evidence**: a `yes` must cite `file:line` within five lines
   of a changed line, otherwise that sample's answer is discarded as invalid
   rather than counted as a violation;
4. reports `p_violation` per question — the share of valid samples that
   found the problem — in `.claude/state/critic.json` and the run log.

There is no verdict: the judge weighs `p` against the thresholds in the
owner's profile (next section). The result is bound to the diff hash; any
further edit makes it stale. Re-running the critic on an unchanged diff
adds samples to the same estimate (the gate pools every run on that diff
from the run log), so re-rolling for a lucky draw does not work.

```bash
scripts/review_gate.sh --dry-run          # which questions apply, critic hash, no model call
scripts/review_gate.sh                    # k samples
KALETA_CRITIC_SAMPLES=5 scripts/review_gate.sh
```

One sample from **another model family** — a local model behind an
OpenAI-compatible endpoint (Unsloth Studio, Ollama, llama.cpp server):

```bash
export KALETA_CROSS_REVIEW=1                              # required for high-risk changes anyway
export KALETA_CROSS_REVIEW_URL=http://localhost:8888/v1   # Unsloth Studio (default); Ollama: http://localhost:11434/v1
export KALETA_CROSS_REVIEW_API_KEY=sk-unsloth-…           # Unsloth Studio: Settings → API; Ollama: none
export KALETA_CROSS_REVIEW_MODEL=unsloth/Qwen3.8-27B-GGUF # default: the first id GET /models lists
scripts/review_gate.sh
```

The local sample counts toward k. It cannot open files or run tests, so
it gets the plan and the diff in its prompt; every diff line carries its
new-side line number, so its `file:line` evidence is checked exactly like
Claude's. Large diffs are cut at `KALETA_CROSS_REVIEW_MAX_CHARS` (default
120 000 characters, about 30k tokens) and the model is told to answer
`na` for what it could not see. The request asks for JSON mode and falls
back to plain output when the server refuses it; a `<think>` block is
dropped before parsing. If the sample was required and the server is not
up, the critic fails (`status: error`, `error_kind: cross_unavailable`)
and the judge escalates instead of quietly continuing with Claude alone.
Raw output lands in `.claude/state/critic-raw-cross.txt`.

Model choices: `KALETA_REVIEW_MODEL` (default `sonnet`) for the Claude
samples; `--model` on the runner for the implementer. The critic hash
(prompt template + question file + models) identifies the critic a
calibration report applies to. The interactive `reviewer` subagent asks
the same questions and explains its answers.

## The judge and the profile

`scripts/harness/judge.py` decides; `gate.py` only collects the evidence.
`decide(inputs, profile)` is a pure function — no I/O, clock or randomness —
and every gate record stores the inputs, the profile and the decision, so
`judge.py replay docs/harness/runs/<plan>.jsonl` recomputes every decision
(CI does this on every PR).

The **profile** `docs/harness/profile.toml` is the owner's law, signed
(`[meta] version, owner, signed`). The gate reads it **as merged on the
merge-base**, not from the working tree: a diff cannot change the law it is
judged by (and touching it is a protected-path veto anyway). Maintainer
sessions read the working tree.

Order of the decision:

1. **Vetoes → escalate, mode D**: protected paths changed outside maintainer
   mode (a move counts as both paths), a secret pattern on an added line
   (untracked files included), the critic reporting secret data, a broken
   run log, critic answers from canned test samples. The session ends;
   there are no further attempts.
2. **Block** (the implementer fixes it): failed hygiene, criteria or
   `verify.sh`; a blocking green-washing pattern; no, stale or broken critic
   run; fewer successful critic samples than the risk class needs (the
   profile's `critic_samples` is a floor `--samples` cannot lower); a
   question with `p >= block`; a question with
   `uncertain <= p < block` for the first `uncertain_rounds` diffs
   ("strengthen the evidence").
3. **Escalate, mode C**: a question that stayed uncertain across more review
   rounds, or a required cross-family sample that could not run. The critic
   cannot settle it, so the owner does.
4. **Done**, with the **autonomy mode of this change**: the risk class of the
   highest-risk changed path (`[risk]`; a plan without executable criteria or
   a harness plan is high) picks the mode in `[autonomy]`; while any
   applicable question is not calibrated the mode is capped at
   `uncalibrated_cap` (B).

| Mode | Meaning |
|---|---|
| A | eligible to merge with audit only — a label while `allow_auto_merge = false` |
| B | the owner merges after reading the decision note (today's behaviour) |
| C | owner approval required; a cross-family critic sample; PR labelled `needs-owner-review` |
| D | stop — a veto was hit |

If the gate itself crashes, or cannot even start (missing file, interpreter
or import failure), the run ends as escalated in mode D with the cause in
`.claude/state/escalated-reason` — never as done, and never as a block that
repeats without counting toward `max-attempts`.

Every run writes `.claude/state/decision.md` in plain English: the outcome,
the mode and why not a freer one, what would change it, the critic's table
and the profile version. `plan_runner.sh --pr` puts it at the top of the PR
body and labels the PR `autonomy:<mode>`. `plan_goal.sh status` shows it.

```bash
uv run python scripts/harness/judge.py check-profile               # is the profile valid and signed?
uv run python scripts/harness/judge.py replay docs/harness/runs/*.jsonl
uv run python scripts/harness/judge.py decide --inputs inputs.json # what-if on recorded inputs
```

Autonomy grows only with evidence: a question counts as calibrated when the
report in `[calibration] report` was made for the current critic hash and
its miss rate's upper bound is at or below `miss_rate_target` (plan
`critic-calibration-set`). Until then nothing is freer than B.

## Calibrating the critic

A threshold means something only when the probability under it is honest.
The calibration set measures the critic on Kaleta's own history; the report
is what lets a question leave the B cap. It costs real money and never runs
in `verify.sh` or on a PR.

**1. Build the cases** (git only, free):

```bash
uv run python scripts/harness/seed_defects.py --dry-run --max-plans 30   # what it would build
uv run python scripts/harness/seed_defects.py --max-plans 30             # write them
```

- A *clean case* is a merged plan PR replayed as `git diff <merge-base> <PR head>`,
  kept only when no `fix…` commit touched the PR's Python sources within 30
  days. That label is a heuristic: a false alarm on a clean case may be a real
  finding. The number to trust is the miss rate on seeded defects.
- A *mutant* applies one operator to a clean case, so exactly one fact changes:
  `M-SCOPE` (drive-by docstring edit in an untouched module), `M-SERVICE-TEST`
  (the tests of a new service function deleted), `M-VIEW-LOGIC` (a query and
  money arithmetic written into a changed view), `M-TENANT` (a new family
  session swapped for the registry's), `M-KAL` (the new scenario and its
  `Covers:` removed), `M-NOTES` (notes claim a test that is not there),
  `M-MIGRATION` (the migration of a model change deleted). The mutated
  question's gold answer is `yes`; the rest copy the clean case.
- A plan and all its variants share one split (70% `calib`, 30% `test`, by
  the plan id). `docs/harness/calibration/test-split.sha256` pins the test
  split; the runner refuses a test split that does not match it.
- Cases live in `tests/harness/critic_cases/` (protected — the implementer
  must not edit the exam). Questions without an operator (`Q-AUTH-SURFACE`,
  `Q-REGRESSION-TEST`, `Q-SECRET-DATA`) stay uncalibrated, so changes that hit
  them stay capped.

**2. Run the calib split and tune thresholds** (real model, k from the profile):

```bash
uv run python scripts/harness/calibrate_critic.py --split calib --dry-run --budget-usd 50
uv run python scripts/harness/calibrate_critic.py --split calib --budget-usd 50
```

Each case is replayed in a temporary worktree: its base, today's critic
questions, profile and hooks laid over it as one commit, the PR's diff and
the mutation on top; `critic.py --base` answers as the gate would. Results
append to `docs/harness/calibration/<split>.cases.jsonl` and a later run
resumes from them; the run stops before a case would cross `--budget-usd`.
The report — `<critic_hash>-<split>.json` and `.md` — gives per question the
miss rate (a violation with p under `uncertain`: it passes unseen), the
false-alarm rate (a clean answer at or above `block`), accuracy, Brier, a
reliability table at the levels k samples reach and ECE, the counterfactual
flip rate and the invalid-evidence rate, every rate with a 95% Wilson
interval. A high-risk case gets a local-model sample (the profile requires
one), which changes the critic hash, so a run can write two reports — one
per hash. `--cross` puts a local sample on every case.

Change `[thresholds]` from the calib report only.

**3. Run the test split once**, after the thresholds are final:

```bash
uv run python scripts/harness/calibrate_critic.py --split test --budget-usd 50
```

A complete test-split report is final for its critic hash: a second run needs
`--force --reason "<text>"`, and the reason goes into the report and
`docs/harness/calibration/forced-runs.log`. Changing a question, a prompt or
the model changes the hash, and the old report stops counting.

**4. Sign the profile.** Point `[calibration] report` at the test report (or a
list of them, one per critic hash), bump `version` and `signed`. The gate
counts a report only when it is the test split, complete, and made for the
hash of the critic that just reviewed the change. A calibrated question no
longer caps the mode at `uncalibrated_cap`; auto-merge stays the owner's
`allow_auto_merge`.

## Run log

Every gate run and every review run appends one record to
`docs/harness/runs/<plan_id>.jsonl` (`scripts/harness/gate_log.py`). The
file is committed with the plan's PR, so the evidence behind a merge stays
next to the code.

- **gate** records: attempt, branch, base, diff hash, the hashes of the plan,
  the checklist and the protected-paths list, the full judge inputs (checks
  with output tails and durations, changed paths, green-washing and secret
  hits, pooled critic answers, prior uncertainty, calibration), the profile
  and where it came from, the decision and the outcome (`block`, `done`,
  `escalated`, `exhausted`). `plan_goal.sh check` runs are marked `dry`.
- **review** records: the full critic result — diff hash, critic hash,
  status, every sample (reviewer, model, cost, turns), `p_violation` with
  evidence per question, advisory findings.
- Every record carries `seq`, `prev` and `sha`: editing, deleting or
  reordering a line breaks the chain. `gate_log.py verify` runs in CI.
- The log is excluded from the diff hash, so writing a record never makes a
  review stale, and it is exempt from the protected-path veto because the
  harness, not the agent, writes it.

```bash
uv run python scripts/harness/gate_log.py report            # outcomes, attempts, cost per plan
uv run python scripts/harness/gate_log.py show <plan_id>    # the last records, in full
uv run python scripts/harness/gate_log.py verify            # hash chain of every log
```

## Changing the harness

The harness is the judge, so the implementer may not change it
([ADR-39](adr/039-measurable-critic-deterministic-judge.md)). Every path in
`docs/harness/protected-paths.txt` is refused by `protect-files.sh`, and the
gate vetoes a diff that changed one of them through Bash (`sed -i`,
`cat >`) — the Edit guard alone does not see those.

The owner changes the harness in **maintainer mode**:

```bash
KALETA_HARNESS_MAINTAINER=1 claude      # hooks inherit this; the agent cannot set it for them
> /implement-plan harness-maintainer-mode
```

- Plans that change the harness say `harness: true` in their frontmatter.
  `/implement-plan` stops unless the session runs in maintainer mode, and
  `scripts/plan_runner.sh` refuses them: the harness is never changed
  headless.
- Every edit let through prints `protect-files: maintainer edit <path>`.
- The gate still judges harness plans (acceptance criteria, `verify.sh`,
  review); the owner reads the diff before merging anyway.
- Exhaustion is terminal: once `result` is `exhausted` the gate stays quiet
  until `scripts/plan_goal.sh start <plan_id>` re-arms the plan.
- A requested cross-family sample (`KALETA_CROSS_REVIEW=1`) that cannot run
  makes the critic fail with `status: error` instead of silently continuing
  with one model family.

The harness has its own tests, next to it and protected with it:
`uv run pytest scripts/harness/tests` (part of `verify.sh`).

## What the gate does NOT protect against

- **A plan with prose-only acceptance criteria.** Older plans (e.g.
  `transactions-notes-field`) list criteria as sentences. The gate warns
  and relies on verify.sh + the reviewer. Rewrite criteria as backtick
  commands (`docs/plans/README.md`) before running a plan headless.
- **Forged critic results.** The agent may run Bash; a determined model
  could write `.claude/state/critic.json` by hand. The Edit/Write tools are
  blocked on that path, the prompt forbids it, and the run log would lack
  the matching review record, but this is a personal repo, not a sandbox.
  In CI use `--bare` and a separate step.
- **Semantic drift.** Everything green, reviewer approved, behaviour
  still not what you meant. That is why merge stays human.

## Other agents: the same gate, a different loop

Nothing here depends on Claude Code to *judge* a plan — the judge is
`scripts/plan_goal.sh check`. Claude Code only adds the `Stop` hook that
calls it automatically and blocks the session. An agent without such a hook
(a local one on Unsloth Studio or Ollama, for instance) can be driven
Ralph-style: arm the plan, run the agent, run `scripts/plan_goal.sh check`,
feed its output back, repeat up to the attempt limit. `plan_runner.sh` only
ships the Claude Code engine today.

## Roadmap for this harness

- Tekton on k3d: `plan_runner.sh` becomes a `Task` (clone → implement →
  review → pr) with the same scripts inside a runner image; Flux keeps
  the pipeline manifests in sync. The scripts already avoid interactive
  git and take everything from env/args for that reason.
- A homelab endpoint (the RTX 4080 box) as the cross-family critic for
  runs where the laptop's local model is not up.
- Ship `logs/plans/*.json` (turns, cost, result) to Loki/Grafana for a
  per-plan cost and success dashboard.
