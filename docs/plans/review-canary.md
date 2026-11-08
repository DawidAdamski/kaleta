---
plan_id: review-canary
title: Canary PRs with a planted defect to measure the CI reviewer and owner attention
area: harness / review
effort: medium
status: draft
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Canary PRs with a planted defect to measure the CI reviewer and owner attention

## Intent
With a green gate, an approving critic and a CI reviewer, it gets easy to
click merge without reading (Parasuraman & Manzey, 2010: automation bias).
The calibration set measures the local critic offline. Nothing measures the
CI reviewer (`pr-review.yml`) on live PRs, or whether the owner still
catches what the automation misses. This plan plants known defects in PRs
that can never reach `main` and scores who caught them.

## Scope
Covers:
- A long-lived branch `canary-base` that tracks `main` and is never merged
  back, guarded by a GitHub branch rule and by `canary.py`, which refuses
  any other base.
- `scripts/harness/canary.py`:
  - `open [--question Q-...]`: picks an archived plan, builds a mutant with
    `seed_defects.py` (`critic-calibration-set`), rebases it onto
    `canary-base`, and opens a PR with an ordinary title and body (no
    "canary" wording). The planted defect is recorded only in the
    git-ignored `logs/canary/<pr>.json`, so no reviewer sees the answer;
  - `score <pr>`: reads the CI review comment and the owner's review
    comments and records `ci_hit`, `owner_hit` (defect named at the right
    file within ±5 lines), time to the owner's review, and the outcome. It
    appends to `docs/harness/canary.jsonl` (hash-chained like the run log)
    and closes the PR;
  - `report`: hit rates per reviewer and per question, with Wilson
    intervals.
- Cadence lives in the profile (`[canary] per_month = 2`). There is no
  scheduler: the owner runs `canary.py open`, or a later scheduled task
  does.
- `docs/goal-mode.md` "Canaries": what they are, why they exist, how to
  score them.

Does **not** cover:
- Blinding the owner fully. The base branch gives a canary away to anyone
  who looks. The CI reviewer is measured blind; the owner measurement is a
  drill, and the report labels it that way.
- Changing the CI reviewer's prompt based on results (follow-up chore).

## Acceptance criteria

- `uv run pytest tests/unit/harness/test_canary_score.py -q`
- `uv run pytest tests/unit/harness/test_canary_refuses_main.py -q`
- `uv run python scripts/harness/canary.py report --help`
- `./scripts/verify.sh`
- `[manual]` Branch rule on `canary-base` set in GitHub; one canary opened,
  reviewed by CI, scored and closed.

## Touchpoints
- `scripts/harness/canary.py` (new), `docs/harness/canary.jsonl` (new)
- `docs/harness/profile.toml` (`[canary]`)
- `.gitignore` (`logs/canary/` is already covered by `logs/`; verify)
- `tests/unit/harness/test_canary_*.py`
- `docs/goal-mode.md`

## Open questions
- *Does a canary PR trigger CI costs?* Yes, one CI review per canary.
  Default cadence of two per month keeps that negligible.
- *What if the owner merges a canary?* It can only merge into
  `canary-base`, which is reset from `main` by `canary.py open`. The score
  records it as `owner_hit = false, merged = true`.

## Implementation notes
_Filled in as work progresses._
