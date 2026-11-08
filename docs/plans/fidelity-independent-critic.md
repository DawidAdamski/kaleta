---
plan_id: fidelity-independent-critic
title: Restyle fidelity reports written by an independent critic, with a measured screenshot difference
area: harness / restyle
effort: medium
status: draft
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
_Filled in as work progresses._
