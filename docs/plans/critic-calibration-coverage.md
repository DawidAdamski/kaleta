---
plan_id: critic-calibration-coverage
title: Critic calibration coverage — seeded defects for every question, label fixes, full calibration run
area: harness / review
effort: medium
status: draft
harness: true
roadmap_ref: ../roadmap.md
---

# Critic calibration coverage — seeded defects for every question, label fixes, full calibration run

## Intent
The first calibration of critic `36ef5368e55e44a3` (2026-11-16, calib split, 17 of 93 cases,
10.31 USD, report `docs/harness/calibration/36ef5368e55e44a3-calib.md`) shows two things.
- **Seeded defects:** the critic caught 12 of 12 (miss rate 0), but only for three questions:
  Q-SCOPE, Q-NOTES-TRUTH and Q-KAL-SCENARIO.
- **No questions calibrated:** with about four mutants per question, the 95% interval on the
  miss rate reaches 0.49, so no question passes the "miss-rate upper bound ≤ 0.10" bar.

The calibration set cannot measure the questions that matter most for autonomy:
- **Q-TENANT-ISOLATION** has 3 mutants in the whole set.
- **Q-SERVICE-TEST** has none. The `M-SERVICE-TEST` operator exists in
  `scripts/harness/seed_defects.py`, but it never produced a case (see Grounding).
- **Q-REGRESSION-TEST, Q-AUTH-SURFACE and Q-SECRET-DATA** have no operator at all.

The 17% false-alarm rate is mostly two labelling problems, not a strict critic. Of the 17
false alarms, 14 come from two causes:
- **Four Q-NOTES-TRUTH alarms on `--m-kal` mutants:** removing a KAL id also makes the
  plan's notes, which name that id, untrue. The mutant changes two facts, so the gold
  "no" is wrong. Two Q-SCOPE alarms on `--m-kal` look like the same cause.
- **Eight alarms on one PR:** these are the Q-SERVICE-TEST and Q-REGRESSION-TEST alarms on
  `debts-loan-linked-exclusion` and its three mutants. That is one underlying PR counted
  four times, labelled clean only by the "no fix commit within 30 days" heuristic.

This plan makes the exam cover every question, fixes the labels, and then runs a full
calibration that can name calibrated questions. It runs **after** the open API PRs
(#435–#440) are merged.

## Grounding (what the code does today)
- **Seeded defects:** `seed_defects.py` `OPERATORS` maps `M-SCOPE`, `M-SERVICE-TEST`,
  `M-VIEW-LOGIC`, `M-TENANT`, `M-KAL`, `M-NOTES` and `M-MIGRATION` to their questions. The
  case counts in `tests/harness/critic_cases/` are m-scope 30, m-notes 30, m-kal 20,
  m-view-logic 4, m-tenant 3, m-migration 3, and m-service-test 0.
- **Why `M-SERVICE-TEST` never fires:** the operator deletes or reverts every test file that
  uses a new service function. It then gives up when a `Covers: KAL-…` id would be orphaned,
  because that would also flip Q-KAL-SCENARIO. Kaleta tests almost always carry `Covers:`
  lines, so in practice it always gives up.
- **The two splits:** `calibrate_critic.py` runs a split and resumes from
  `docs/harness/calibration/<critic_hash>-<split>.cases.jsonl`. The test split runs once per
  critic hash, and its case ids must hash to `docs/harness/calibration/test-split.sha256`.
- **Who answers:** the critic's k=3 samples are Claude (`KALETA_REVIEW_MODEL`, default
  sonnet). With `KALETA_CROSS_REVIEW=1`, one of the three instead comes from a local model
  behind an OpenAI-compatible endpoint (today Qwen on Unsloth Studio). That sample is there
  for *diversity*, a second model family that does not share Claude's blind spots, not for
  strength. `critic_hash` includes the model ids, so each configuration is its own critic
  with its own calibration. The 2026-11-16 run shows both: `36ef5368e55e44a3` (17 cases)
  and `613e8b9ab733ffd9` with the local sample (3 cases). The gate runs in this session
  used all-Claude samples.
- **Protected paths:** `scripts/harness/*`, `docs/harness/*` and
  `tests/harness/critic_cases/*` are all protected (`docs/harness/protected-paths.txt`). The
  work needs a `KALETA_HARNESS_MAINTAINER=1 claude` session, never `plan_runner.sh`.
- **Uncommitted results:** the 2026-11-16 calibration results sit untracked in
  `docs/harness/calibration/`:
  - `36ef5368e55e44a3-calib.{json,md}`
  - `613e8b9ab733ffd9-calib.{json,md}` (3 cases from a local sample)
  - `calib.cases.jsonl`

## Scope

### 1. Keep the first calibration
Commit the 2026-11-16 calibration files listed above as they are. They are the baseline the
later runs are compared with.

### 2. Fix the labels that make mutants change two facts
- **`M-KAL`:** when the removed KAL id also appears in the plan's `## Implementation notes`
  or acceptance criteria, either remove it there too and mark Q-NOTES-TRUTH and Q-SCOPE
  "not applicable" for that mutant, or skip the case. It must stay a one-fact change.
  Rebuild the `--m-kal` cases.
- **Case-family weighting:** the report counts a clean case and its mutants as independent
  samples for questions the mutation does not touch. Report the clean-case rates per
  underlying PR, with mutants of the same PR collapsed for unaffected questions. This
  stops one mislabelled PR from counting four times.
- **`debts-loan-linked-exclusion`:** check by hand whether that PR really lacks service and
  regression tests. If it does, relabel it, and record the decision as a gold-label change
  with its reason.

### 3. Seed defects for every question
At least 20 mutants per question in the calib split for Q-TENANT-ISOLATION, Q-SERVICE-TEST,
Q-REGRESSION-TEST and Q-AUTH-SURFACE. Q-SECRET-DATA needs at least 10, because it is mostly
a deterministic veto.
- **`M-SERVICE-TEST` (repair):** remove only the test *functions* that call the new service
  function, not whole files. Keep every `Covers:` id that another test in the file still
  carries. When a removed function is the only carrier of an id, move the id to a remaining
  test's docstring in the same file, so Q-KAL-SCENARIO does not flip.
- **`M-TENANT` (widen):** besides `{family} → {public}`, add one more variant: a new v1
  route whose session comes from the wrong dependency (not `kaleta.api.deps.get_session`).
  Use only PRs that add API routes.
- **`M-REGRESSION-TEST` (new):** on a PR whose branch or title marks it a fix (`fix/…`,
  `fix(`), remove the test the PR added for the bug, and keep the fix.
- **`M-AUTH-SURFACE` (new):** on a PR that adds a route under `/api/v1`, mount the new route
  outside the authenticated `v1_router`, or drop the `require_api_auth` dependency it gets.
- **`M-SECRET` (new):** plant a high-entropy, clearly fake credential that matches one of
  `profile.toml`'s `secret_patterns` in a non-excluded file. Example: an `sk-ant-…` string
  made of a fixed fake alphabet. It must not be a real key.
- **Splits:** new cases go to the **calib** split. Cases go to the test split only through
  a new, recorded `test-split.sha256`, and only after step 5's question changes are final.
  The test split is never looked at before then.

### 4. Look again at Q-SERVICE-TEST after the label fixes
- **Start from the re-run:** step 2 alone may explain most of Q-SERVICE-TEST's 5/10 false
  alarms. Re-run the calib split for that question first.
- **Narrow the wording if needed:** if the rate after step 2 is still above 0.15, narrow
  the question in `docs/harness/critic-questions.toml` to logic a test should reach (a new
  branch, a new raise, a new public method). A changed docstring or log line is not enough.
  A changed question is a new critic hash, so step 5 runs on it.

### 5. Full calibration run (owner-billed)
- **Calib split:** run all cases of the calib split on the final critic hash, with
  `--budget-usd` set by the owner. The expected cost is about 0.6 USD per case at k=3.
- **Test split:** run it **once**, on the same hash.
- **Readme:** record in `docs/harness/README.md` which questions are now calibrated (miss
  upper bound ≤ 0.10) and which are not. Nothing turns on `allow_auto_merge`; that stays
  the owner's decision.

## Out of scope
- Changing the judge, the profile thresholds (`block` / `uncertain`) or `allow_auto_merge`.
- New critic questions (for example a general logic-bug question). This plan measures the
  existing eight, plus Q-VIEW-LOGIC and Q-MIGRATION where they already have cases.
- Review-canary (`review-canary.md`): a separate plan, which can reuse the new operators.
- Making the gate's critic cheaper (fewer samples, smaller model).

## Acceptance criteria
- `uv run pytest scripts/harness/tests -q`
- `uv run python scripts/check_doc_links.py`
- Unit tests in `scripts/harness/tests/` exercise each new or repaired operator on a small
  fixture repo. Each test checks that the operator changes exactly one question's gold
  answer, and that `M-SERVICE-TEST` keeps every `Covers:` id carried.
- The rebuilt case set has at least 20 calib mutants each for Q-TENANT-ISOLATION,
  Q-SERVICE-TEST, Q-REGRESSION-TEST and Q-AUTH-SURFACE, and at least 10 for Q-SECRET-DATA.
  `seed_defects.py --dry-run` shows the counts, which are recorded in Implementation notes.
- [manual] The owner runs the full calib split and then the test split once on the final
  hash. Both reports are committed under `docs/harness/calibration/`, and
  `docs/harness/README.md` names the calibrated questions.

## Touchpoints
- `scripts/harness/seed_defects.py`: the new and repaired operators, the `M-KAL` label fix.
- `scripts/harness/calibration.py` or `calibrate_critic.py`: per-PR collapsing for
  unaffected questions in the report.
- `scripts/harness/tests/`: operator tests.
- `tests/harness/critic_cases/`: rebuilt cases. These are generated, never hand-edited.
- `docs/harness/critic-questions.toml`: only if step 4 narrows Q-SERVICE-TEST.
- `docs/harness/calibration/`: the 2026-11-16 baseline, and later reports.
- `docs/harness/README.md`, `docs/plans/README.md` (harness table).

## Open questions
- **How should the calibration bar be reached?** Default: 20+ mutants per question in the
  calib split. That bounds the miss rate's upper interval near 0.16 at 0/20, and near 0.11
  at 0/30. Push to 30 for Q-TENANT-ISOLATION, because it is the security question.
- **Case-family collapsing: in the report only, or in the gold labels too?** Default:
  report only. The labels stay per case.
- **`M-SECRET`'s fake key: is it safe with the repo's own secret scanners?** Default: put
  it only in `mutation.patch` under `tests/harness/critic_cases/`, never in a source file
  on a branch, and add that path to the scanners' allowlist if they flag it.
- **Which configuration is calibrated: all-Claude, or with the Qwen cross sample?**
  Default: the one the gate actually runs with. If the gate is meant to run with
  `KALETA_CROSS_REVIEW=1`, calibrate that hash. A weak local model is acceptable as long as
  its sample is valid (parsable, with evidence that resolves). The report's invalid-evidence
  rate per reviewer shows it. Report per-reviewer agreement too, so a cross sample that only
  adds noise is visible.
- **Budget for step 5?** The owner decides. About 0.6 USD × (calib cases + test cases),
  roughly 60–90 USD for the full set after the new mutants.

## Implementation notes
