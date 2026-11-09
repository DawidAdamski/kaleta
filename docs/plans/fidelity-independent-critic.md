---
plan_id: fidelity-independent-critic
title: Restyle fidelity reports written by an independent critic, with a measured screenshot difference
area: harness / restyle
effort: medium
status: in-progress
harness: true
roadmap_ref: ../roadmap.md#5-engineering-hygiene
---

# Restyle fidelity reports written by an independent critic, with a measured screenshot difference

## Intent
`scripts/restyle_fidelity.py check` checks that a report exists, matches the
current code, has no `open` row, and gives a reason for every `deviation`.
But the report is written by the implementer that built the screen. That is
self-assessment, which
[ADR-39](../adr/039-measurable-critic-deterministic-judge.md) rules out, and
it is part of why screens kept drifting from the artboards. This plan moves
the report to a separate critic process and adds a number that does not
depend on anyone's eyes.

## Scope
Covers:
- `restyle_fidelity.py critique <id|all>`: a fresh read-only critic session
  (`claude -p`, same allow-list style as `critic.py`). It gets only the two
  screenshots from `.fidelity/<id>/`, `docs/design/restyle/artboards/<id>.html`
  and the screen's view sources, never the implementer's conversation. It
  writes the report rows. The report header records `author: critic`, the
  critic run id, the model, and the sha256 of both screenshots.
- **Measured difference** in `shoot`: both screenshots are resized to the
  artboard width and split into a 4×4 grid, and the mean absolute
  difference per tile goes into the report header (`tiles`) together with
  the whole-screen value.
- `check` additionally requires: `author: critic`; screenshot hashes equal to
  the files in `.fidelity/<id>/` (so shots and report match); and every tile
  above the profile's `[fidelity] tile_threshold` covered by a `deviation`
  row that names it. Until the owner sets thresholds from observed values,
  `tile_threshold` is unset and `check` only requires the three worst tiles
  to be named.
- `docs/design/restyle/fidelity/**` and `scripts/restyle_fidelity.py` (it
  judges fidelity, so it is part of the harness) are added to
  `protected-paths.txt`. The executor runs `shoot` and `critique`; it does
  not write reports or change the check.
- A `fidelity` record per `check` in the run log (`gate-audit-log`).
- `docs/review-checklist.md` §7: the reviewer checks author and hashes
  instead of spot-checking three rows by hand.

Does **not** cover:
- Changing the artboards, the shooting harness (seeded instance, ports) or
  the list of target artboards.
- A perceptual metric beyond tile differences (SSIM etc.). Revisit once tile
  data exists.
- Fixing the screens themselves (restyle plans).

## Acceptance criteria

- `uv run pytest tests/unit/harness/test_fidelity_tiles.py -q`
- `uv run pytest tests/unit/harness/test_fidelity_check_author.py -q`
- `grep -q "docs/design/restyle/fidelity" docs/harness/protected-paths.txt`
- `grep -q "author: critic" docs/review-checklist.md`
- `./scripts/verify.sh`
- `[manual]` `restyle_fidelity.py shoot 2a && restyle_fidelity.py critique 2a && restyle_fidelity.py check 2a` passes on the current code, and the report header shows tiles and the critic id.

## Touchpoints
- `scripts/restyle_fidelity.py`
- `docs/harness/protected-paths.txt`, `docs/harness/profile.toml` (`[fidelity]`)
- `docs/review-checklist.md` §7, `docs/plans/README.md` (fidelity paragraph)
- `tests/unit/harness/test_fidelity_*.py` (synthetic images, report parsing)

## Open questions
- *Image library.* Default: Pillow plus numpy if they are already in the
  dependency graph (check `uv.lock`). Otherwise decode PNGs with the
  already-present Playwright stack. Adding a dependency needs an owner
  decision.
- *Seed data vs. artboard sample data.* Text differs by design, so tile
  differences have a floor. Default: thresholds come from the observed
  values on screens the owner accepts, recorded in the profile.
- *Existing reports* (13 under `docs/design/restyle/fidelity/`). Default:
  regenerate them all with `critique all` in this plan's PR.

## Implementation notes

**Open questions, resolved by their defaults.**
- *Image library:* Pillow only. It is already in the dependency graph
  (`types-qrcode` in the dev group, `matplotlib` in the `forecast` extra) and
  installed by `uv sync --group dev`, which `verify.sh` requires. numpy is
  only in the `forecast` extra, so it is **not** used; `ImageChops` +
  `ImageStat` do the arithmetic. No dependency added. Caveat: Pillow is a
  transitive dev dependency; if `types-qrcode` ever leaves the dev group,
  the owner should declare `pillow` there directly.
- *Thresholds:* `[fidelity]` is in the profile with `tile_threshold`
  commented out (unset), so `check` requires the three worst tiles to be
  named. Profile bumped to `version = 2`, `signed = 2026-11-09`.
- *Existing reports:* all 13 regenerated with `shoot all` + `critique all`
  in this PR (see "Regenerated reports" below).

**Grid alignment (a design decision made after looking at the shots).** The
first version split each picture into quarters of its *own* height. On `2a`
the app is a full-page shot 4022 px tall and the card 811 px, so the
artboard's header tile was compared with the ledger's fifteenth row. Now the
app is resized to the artboard's width and laid over the artboard from the
top: the artboard's frame is what is gridded, rows that run on below the
card are not compared, and an app shorter than the card is padded with
white, which counts against it. Only the artboard's own (first) viewport is
measured; `3f`'s phone viewport is still in front of the critic.

**Tile naming.** Rows A–D top to bottom, columns 1–4 left to right (`A1` is
top left). A deviation row names a tile by containing the word "tile(s)"
and the id, in the Element or Note cell; `match`/`open` rows do not count.

**Protected paths.** `scripts/restyle_fidelity.py` is fully protected.
`docs/design/restyle/fidelity/*` is `written-by-harness:`, not plainly
protected: a restyle plan *must* run `shoot` and `critique`, which change
the report, and a plain entry would veto every such diff. So the agent's
Edit/Write is blocked but a Bash write is not. Residual route: an
implementer could still `sed` a report. `check` catches a report whose
author, shot hashes or tiles disagree with the screenshots on disk, but
not rows edited while the header is left alone. Closing that needs the
critique to log a sha of the report it wrote (in the run log) for `check`
to compare. That is a follow-up for the owner, not in this plan's Scope.

**Critic session.** `claude -p --permission-mode dontAsk`, `--allowedTools`
= `Read(//…)` on `.fidelity/<id>/**`, the artboard file and the screen's
source paths only; `--disallowedTools` = Bash/Edit/Write/MultiEdit/
NotebookEdit/WebFetch/WebSearch/Task/Agent plus `Read` on the reports
directory (so the critic cannot copy the old report). The project and user
settings carry no broad allow rules (checked). `KALETA_CRITIC_SESSION=1` as
in `critic.py`. Model: `--model`, else `KALETA_FIDELITY_MODEL`, else
`KALETA_REVIEW_MODEL`, else `sonnet`. Raw output goes to
`.fidelity/<id>/critic-raw.json`. The run id is the session's `session_id`.

**Run log.** `check` appends one `fidelity` record per artboard to the
armed plan's log (`.claude/state/active-plan`, else the `plan/<id>`
branch). Outside a plan, nothing is logged and `check` says so, which keeps
`main` free of log churn from ad-hoc checks.

**Out-of-scope fix in the same file (Chore-inbox rule: same file, trivially
small, own commit).** `shoot` had been broken on `main` since `7a8b012f` put
`/api-docs` behind a debug flag: the ephemeral app's readiness probe never
got its 200 and every shoot timed out. The probe now waits on `/health`.
Without this the plan's own `shoot` criterion could not run.

**Working Agreement §12 and the restyle README.** These are not in
Touchpoints, but §12 told the implementer to *write* the report, which the
Scope bullet "it does not write reports" (and now the protect hook) forbids.
Only §12's procedure sentence and the README's command block were changed,
to shoot → critique → check.

**Manual criterion: state on the current code.** `shoot 2a && critique 2a`
works end to end, and the header shows `author: critic`, `critic_run`,
`critic_model`, `shots` and `tiles`. `check 2a` does **not** pass. The
independent critic reports four `open` rows on the real screen (Export
button missing, selected-row tint grey not warm, amounts with hyphen-minus
and dot decimals, tags column chips). The tile requirement itself passes.
The old hand-written report had all of these as `match` or `deviation`,
which is exactly the drift this plan was written to expose. Fixing the
screens is "Does not cover" here, so this criterion is left to the owner
together with the restyle plans.

**Harness test touched.** `scripts/harness/tests/test_judge.py::test_note_for_the_owner`
renders the decision note from the real profile and asserted `Profile v1`.
The profile is now v2 (this plan adds `[fidelity]`), so the expected literal
became `Profile v2`. The assertion is just as strict; only the version changed.

**Regenerated reports (2026-11-09, `shoot all` + `critique all`, sonnet,
~0.25 USD and ~45 s per artboard).** All 13 now carry `author: critic`.
`check all` is red: 41 rows across the 13 screens are `open` (1c 2, 1d 2,
1f 4, 2a 1, 2b 2, 2c 4, 2d 3, 3a 4, 3b 6, 3c 4, 3d 4, 3e 4, 3f 1). The
hand-written reports had passed. Fixing the screens is not this plan's
work, so this is the honest starting state for the restyle plans. Two
observations for the owner:
- *One sample is noisy.* `2a` critiqued twice on the same shots gave 4 open
  rows, then 1. Several samples with a majority (as `critic.py` does) would
  be the next step, together with the `tile_threshold` calibration.
- *2d* named its worst tile (D4) in an `open` row but in no `deviation`
  row, so `check` also reports the tile. That is the specified behaviour
  (the prompt asks for both), and it is left as is.
