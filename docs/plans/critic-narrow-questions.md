---
plan_id: critic-narrow-questions
title: Critic answers narrow typed questions with evidence and a sampled probability, never a verdict
area: harness / review
effort: medium
status: draft
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Critic answers narrow typed questions with evidence and a sampled probability, never a verdict

## Intent
Today one LLM returns `approve` / `changes`, and the gate obeys it. That
makes the reviewer the judge, and its uncertainty disappears into a binary
answer (`hosted-supabase-rollout`: `approve` with three findings about
missing tests). Per [ADR-39](../adr/039-measurable-critic-deterministic-judge.md)
the critic becomes an expert witness. It answers narrow questions, backs
every "violation" with `file:line` evidence that code can check, and its
strength is the agreement of *k* independent samples. Verbalised
confidence is not used.

## Scope
Covers:
- **Question set** `docs/harness/critic-questions.toml` (owner-owned,
  protected). Each question has `id`, `text`, `checklist_section`,
  `applies_to` (path globs; empty means always), and `evidence` (what has to
  be cited). Initial set:
  - `Q-SCOPE`: the diff changes something outside the plan's Scope or
    inside "Not in scope", without a reason in Implementation notes;
  - `Q-SERVICE-TEST`: new or changed logic in `src/kaleta/services/**` has
    no unit or integration test that exercises it;
  - `Q-REGRESSION-TEST`: a bug fix has no test that would fail without
    the fix;
  - `Q-VIEW-LOGIC`: queries or business computation added under
    `src/kaleta/views/**`;
  - `Q-TENANT-ISOLATION`: a new query or session can read or write outside
    the current family's schema (public session for family data, raw SQL
    with user input, unvalidated schema identifier);
  - `Q-AUTH-SURFACE`: a new route or handler is reachable without the
    auth-gated router, or a state change is possible on a cookie alone;
  - `Q-MIGRATION`: model change without a migration, or a migration that is
    not reversible;
  - `Q-KAL-SCENARIO`: new user-facing behaviour without a `KAL-` scenario
    or `Covers:` reference;
  - `Q-NOTES-TRUTH`: Implementation notes claim something the diff
    contradicts (a test that does not exist, a decision not implemented);
  - `Q-SECRET-DATA`: secrets, real personal or financial data, or
    database dumps in the diff.
- `scripts/harness/critic.py`, which `scripts/review_gate.sh` calls (the
  script stays as a thin wrapper so the gate and docs keep working):
  1. selects the applicable questions from the changed paths;
  2. runs **k samples** (`KALETA_CRITIC_SAMPLES`, default 3). Each is a fresh
     read-only `claude -p` with the same tool allow-list as today and a
     JSON schema of one answer per question:
     `{id, answer: yes|no|na, evidence:[{file,line}], note}`. With
     `KALETA_CROSS_REVIEW=1`, one sample comes from the Cursor CLI model and
     counts toward *k*;
  3. **validates evidence deterministically**: a `yes` (violation) whose
     evidence does not point at a changed file, at a changed hunk or within
     ±5 lines of one, is an *invalid sample* for that question, not a
     violation. Invalid counts are recorded;
  4. aggregates `p_violation = violations / valid samples` per question,
     plus `k_valid` and `agreement`;
  5. writes `.claude/state/critic.json` v2 with `diff_hash`, critic hash
     (sha of prompt template, question file and model ids), questions,
     advisory free-form findings, and per-sample cost. It appends a
     `review` record to the run log (`gate-audit-log`).
- **There is no verdict field.** Until `judge-profile-and-autonomy` lands,
  `dod-gate.sh` uses a transitional rule: block when any question has
  `p_violation >= 0.67` (2 of 3), and list that question's evidence as the
  reason. A question with `0 < p < 0.67` produces a non-blocking warning.
  The old `review-verdict.json` is no longer read.
- `.claude/agents/reviewer.md` (the interactive reviewer) gets the same
  question set, so the explainable review and the gate stay aligned.
- Offline tests: `KALETA_CRITIC_FAKE=<dir>` makes `critic.py` read canned
  sample responses instead of calling a model.

Does **not** cover:
- Thresholds per question, risk classes and autonomy modes (next plan).
- Proving the critic is calibrated (`critic-calibration-set`).
- The CI reviewer (`pr-review.yml`) keeps its current prompt. Aligning it
  is a chore once calibration shows which questions it should ask.
- A local small model as a critic (future, after data exists).

## Acceptance criteria

- `test -f docs/harness/critic-questions.toml`
- `uv run pytest tests/unit/harness/test_critic_aggregate.py -q`
- `uv run pytest tests/unit/harness/test_critic_evidence.py -q`
- `uv run pytest tests/unit/harness/test_critic_question_selection.py -q`
- `uv run pytest tests/unit/harness/test_dod_gate_transitional_rule.py -q`
- `KALETA_CRITIC_FAKE=tests/unit/harness/fixtures/critic_samples uv run python scripts/harness/critic.py --plan harness-fixture --dry-run`
- `./scripts/verify.sh`
- `[manual]` One real run on an open plan branch: `critic.json` has a
  `p_violation` for each applicable question, cost per sample is recorded,
  and the run log has the review record.

## Touchpoints
- `docs/harness/critic-questions.toml` (new)
- `scripts/harness/critic.py` (new), `scripts/review_gate.sh` (wrapper)
- `.claude/hooks/dod-gate.sh` (reads `critic.json`, transitional rule)
- `.claude/agents/reviewer.md`
- `tests/unit/harness/` (new tests and `fixtures/critic_samples/`)
- `docs/goal-mode.md` ("The reviewer(s)" section rewritten)

## Open questions
- *k and cost.* Default k=3 for every plan, because k=1 gives p ∈ {0, 1},
  which is a verdict in disguise. The cost of k is visible in the run log;
  the next plan can lower k for the low-risk class.
- *Model.* Default `KALETA_REVIEW_MODEL=sonnet` (as today). The implementer
  is usually a bigger Claude model, so the samples are same-family; the next
  plan makes a cross-family sample mandatory for the high-risk class.
- *Does `na` count as valid?* Default: yes, as "no violation". Only `yes`
  needs evidence.
- *Free-form findings* stay as advisory text for the implementer. They
  never block.

## Implementation notes
_Filled in as work progresses._
