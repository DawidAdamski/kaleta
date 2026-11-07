---
adr_id: "039"
title: "Separation of Powers in the Coding Loop: Measurable Critic, Deterministic Judge, Owner-Signed Profile"
status: proposed
---

# ADR-39: Separation of Powers in the Coding Loop — Measurable Critic, Deterministic Judge, Owner-Signed Profile

- **Context**: Goal mode ([goal-mode.md](../goal-mode.md)) already separates
  the implementer from the judge: `.claude/hooks/dod-gate.sh` is plain code,
  the harness is read-only for the agent, and merge stays human. One link is
  not built that way. `scripts/review_gate.sh` asks one LLM for a binary
  `approve` / `changes`, and the gate passes that verdict through as-is. So
  the reviewer is not an expert witness but the judge itself, which is
  exactly the configuration "Mierzalny krytyk" (J. Marcinkowski,
  5 Nov 2026) and the LLM-as-a-judge literature warn against (Zheng et al.,
  NeurIPS 2023: position, length and self-preference bias; Xiong et al.,
  ICLR 2024: verbalised confidence is overconfident). Observed in this repo:
  - the verdict for `hosted-supabase-rollout` is `approve` while its own
    findings say a pool-settings regression "would pass CI" and ask to
    confirm a missing unit test. The binary verdict hid the uncertainty;
  - nothing is measured: `review-verdict.json` is overwritten on every run in
    the git-ignored `.claude/state/`, so the reviewer's miss rate on approved
    PRs is unknown;
  - autonomy is set per process, not per change: every plan ends the same way
    (gate passes, the owner merges), whether it touches `alembic/` and auth
    or only locale files;
  - escalation to a human is only something the implementer can ask for
    (`plan_goal.sh block`). The judge never escalates on uncertainty, only
    once attempts run out, and `exhausted` is not terminal (state seen:
    `attempts=7`, `max-attempts=6`, `result=done`);
  - restyle fidelity reports are written by the implementer that built the
    screen: self-assessment;
  - the cross-family reviewer is silently skipped when its CLI is missing.

- **Decision**: the loop follows four roles with hard boundaries.
  1. **Executor**: the implementer agent. It proposes a diff inside the
     plan's scope and never assesses its own work, including fidelity reports.
  2. **Critic (expert witness)**: answers *narrow, typed questions* from
     `docs/harness/critic-questions.toml` ("does the diff leave the plan's
     Scope?", "does new service logic have a unit test?", "does a new query
     bypass family isolation?" …). Each answer is `yes | no | na`, with
     `file:line` evidence that is checked deterministically. Its strength is
     a probability `p_violation`, taken as the share of *k* independent
     samples (fresh contexts; for high-risk changes one of them from another
     model family — a local model behind an OpenAI-compatible endpoint such
     as Unsloth Studio or Ollama) that report a violation, not as
     verbalised confidence. The critic **never returns a
     verdict**.
  3. **Judge**: `scripts/harness/judge.py`, a pure function
     `decide(inputs, profile) -> Decision` called by the Stop hook. It runs
     vetoes first (they cannot be outweighed), then per-question thresholds,
     then the autonomy mode for *this* change from its risk class and
     signals. Outcomes are `done(mode)`, `block(reasons)` (the executor can
     fix it) and `escalate(reasons)` (a first-class "hand to the owner"
     baseline, not a failure). Every decision is written to a tamper-evident
     run log and can be replayed to the same result.
  4. **Legislator**: the owner. `docs/harness/profile.toml` (vetoes, risk
     classes, thresholds, autonomy per class), the question set, the review
     checklist and the calibration gold labels are versioned like code,
     protected from the agent, and change only in maintainer mode (an
     environment variable set by the human who launches the session, which
     the agent cannot set for the hooks).
  5. **Autonomy grows only with evidence.** A question counts as
     *calibrated* only when a calibration report for the current critic
     (prompt + model + question hash) shows its miss rate under the
     profile's target, at the upper bound of a 95% Wilson interval, on a
     held-out test split. Uncalibrated questions cap a change at mode B
     (today's behaviour). Auto-merge (mode A) stays disabled in the profile
     until the owner turns it on based on such a report.

- **Autonomy modes** (per change, chosen by the judge):

  | Mode | Meaning |
  |---|---|
  | A | Eligible to merge with audit only (label only until `allow_auto_merge = true`) |
  | B | Owner merges after reading the judge's decision note (status quo) |
  | C | Owner approval required, cross-family critic sample mandatory, PR labelled `needs-owner-review` |
  | D | Stop: veto hit (protected path without maintainer mode, secret, forbidden pattern) |

- **Consequences**:
  - Critic cost scales with *k* (default 3). It is recorded per sample in
    the run log, so the price of caution is visible.
  - Most of what the reviewer judged by prose becomes either a
    deterministic veto or a narrow question with a measured error rate.
  - The run logs and the calibration set double as a training set for a
    small local decision model as a cheaper critic later. That is out of
    scope here.
  - Harness plans (`harness: true` in frontmatter) are never run headless.
    They are implemented in an interactive maintainer session.

- **Rejected alternatives**:
  - *Ask the LLM for its confidence*: overconfident and not
    threshold-able (Xiong et al. 2024).
  - *MCDA ranking (PROMETHEE II) as in the talk*: the loop judges one
    candidate diff, not a choice among proposals. Vetoes plus calibrated
    thresholds give the same guarantees with less machinery. Revisit if the
    runner ever produces competing diffs for one plan.
  - *Turn auto-merge on now*: there is no evidence yet for any risk class.
  - *A stronger single reviewer model*: a smarter model does not replace
    separation of powers, and same-family models fail in the same places.

- **Implemented by** (in order): `harness-maintainer-mode`,
  `gate-audit-log`, `critic-narrow-questions`,
  `judge-profile-and-autonomy`, `critic-calibration-set`,
  `fidelity-independent-critic`, `review-canary`. See the
  [plans index](../plans/README.md).
