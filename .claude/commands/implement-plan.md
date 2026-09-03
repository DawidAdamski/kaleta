---
description: Implement one plan from docs/plans/ in goal mode — the Stop hook is the Definition-of-Done judge
argument-hint: <plan_id> [--max-attempts N]
---

Implement the plan `docs/plans/$ARGUMENTS.md` end to end, in goal mode.

## No plan given?

If the argument above is empty (the command was invoked as plain
`/implement-plan`): run `scripts/plan_goal.sh list draft`, show the
table, recommend one plan (smallest effort first; prefer plans whose
acceptance criteria are executable backtick commands), and ask the user
which plan to take. Then STOP and wait for the answer — never arm a plan
the user did not pick. Once they answer, continue below with that plan id.

## Contract

- The plan is the scope contract (Working Agreement §1). Implement ONLY
  what its Scope covers; "Not in scope" / "Out of scope" is binding.
- Do not ask questions. Every plan lists Open questions with defaults —
  take the default, record the decision in the plan's
  `## Implementation notes`. If something is truly impossible without a
  human decision, run `scripts/plan_goal.sh block "<reason>"` and stop.
- A Stop hook (`.claude/hooks/dod-gate.sh`) judges every attempt to
  finish. It runs the plan's executable acceptance criteria,
  `./scripts/verify.sh` (with `--e2e` when views changed), a
  green-washing check, and requires a fresh independent review verdict.
  When it blocks you, read the reason, fix, and finish your turn again.
  You cannot talk your way past it — only make it pass.

## Steps

1. `scripts/plan_goal.sh start $ARGUMENTS` — arms the gate, creates
   `plan/<plan_id>` from main if needed, flips the plan to
   `status: in-progress`.
2. Read the plan fully, then `AGENTS.md` (Working Agreement), and the
   touchpoint files it lists. Check `docs/bdd.md` for the related
   `KAL-` scenarios.
3. Work in small commits on the plan branch: model/schema → migration
   (new revision only, never edit existing ones) → service → API/view →
   i18n keys (`en.json` + `pl.json`) → tests. New behaviour = new or
   updated `KAL-` scenario in `docs/bdd.md`, tagged `@automated` only
   when a test covers it, with `Covers: KAL-XXX-NNN` in the test docstring.
4. Use the project subagents where they fit: `migration-creator`
   after model changes, `i18n-verifier` after view changes,
   `test-runner` for tests, `docs-writer` if docs need an update.
5. Fill in `## Implementation notes` in the plan: decisions, resolved
   open questions, anything a reviewer must know.
6. Run `./scripts/verify.sh` yourself (add `--e2e` if you touched
   `src/kaleta/views/`). Fix until green.
7. Run `./scripts/review_gate.sh` — an independent reviewer that did
   not write this code. Fix every finding, re-run until it approves.
   (If `KALETA_CROSS_REVIEW=1` is set, a second reviewer from another
   model family must approve too.)
8. Commit. Then finish your turn with a short report: what was done,
   the verify.sh tail, the review verdict, manual acceptance criteria
   left for the owner, and the exact `gh pr create` command to open the
   PR (do not push or open the PR yourself unless the user asked).

Never: add `skip`/`xfail`, loosen assertions, add `ignore_imports`,
replace real types with `Any`, edit archived plans or applied migrations,
or touch the harness files (`.claude/hooks/`, `.claude/settings.json`,
`scripts/verify.sh`, `scripts/review_gate.sh`, `scripts/plan_goal.sh`).
