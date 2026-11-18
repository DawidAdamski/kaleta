---
plan_id: archive-image-links
title: Image links survive plan archiving; the local link check and verify catch what mkdocs --strict catches
area: docs, harness
effort: small
status: archived
archived_at: 2026-11-17
harness: true
roadmap_ref: ../../roadmap.md
---

# Image links survive plan archiving; the local link check and verify catch what mkdocs --strict catches

## Intent
The docs site (`.github/workflows/pages.yml`, `uv run mkdocs build --strict`) has failed on
every push to `main` since about 2026-11-09. The last green deploy was `ae8990c3` (#406).
`mkdocs --strict` aborts on three warnings:

```
plans/archive/import-api-endpoint.md                  → ../images/import-ui-vs-api.svg
plans/archive/import-mbank-transfer-account-suffix.md → ../images/import-ui-vs-api.svg
plans/archive/import-pipeline-service.md              → ../images/import-ui-vs-api.svg
```

The image is `docs/images/import-ui-vs-api.svg`. From `docs/plans/`, `../images/…` was right;
after archiving into `docs/plans/archive/` it has to be `../../images/…`.

There are two root causes, and both share one regex:
- **The archiver skips images:** `scripts/plan_archive.sh` rewrites a plan's relative links
  when it moves the plan one directory down. Its pattern is `(?<!!)\[…\]\(…\)`, which
  deliberately skips image links (`![…](…)`), so they are left pointing one level too high.
- **The link checker skips images too:** `scripts/check_doc_links.py`, which `verify.sh`
  runs, uses the same `(?<!!)` pattern (`MARKDOWN_LINK`). A broken image link passes
  locally and in the gate, and only the Pages workflow, which no PR waits on, sees it.

Fix the archiver so the next plan with a picture archives cleanly. Make the local check see
image links so this cannot reach `main` again, and repair the three archived plans.

## Scope
- **Archiver:** in `scripts/plan_archive.sh`, the relative-link rewrite also handles image
  links. A `![alt](../../x)` target becomes `![alt](../../../x)` under the same rules as `[label]`
  links. A bare same-directory image (`![alt](img.svg)`) moves the same way a bare `.md`
  sibling does.
- **Link checker:** `scripts/check_doc_links.py` also checks image links (`![…](…)`). A
  relative target that does not exist is an error with file and line, like a broken `.md`
  link. External URLs and `data:` stay skipped (`SKIP_URL_PREFIXES`).
- **Repair:** in the three archived plans above, `../images/import-ui-vs-api.svg` becomes
  `../../images/import-ui-vs-api.svg`. `docs/plans/archive/*` is protected ("Frozen
  history"), so this is the one deliberate edit of history, done in a
  `KALETA_HARNESS_MAINTAINER=1` session and named in the commit message. The plans' text
  stays as it is; only the three image paths change.
- **Tests:** none exist yet for either script, so the new ones go in `tests/unit/harness/`
  next to the other script tests.
- **Coverage gap:** check whether any other link kind passes `check_doc_links.py` but fails
  `mkdocs --strict`. Fix it in the checker, or record why it is out of scope.

## Out of scope
- Running `mkdocs build --strict` in `verify.sh` or as a required PR check. It needs the
  mkdocs dependencies in the gate's environment and adds build time. If the checker
  covering image links proves not enough, that belongs in a separate plan.
- The INFO-level "unrecognized relative link" notes (`adr/`, `plans/archive/`, `artboards/`
  and similar directory links). They do not fail `--strict`.
- Moving `import-ui-vs-api.svg`, or any other asset.

## Acceptance criteria
- `uv run python scripts/check_doc_links.py`
- `uv run pytest tests/unit/harness/test_doc_links.py tests/unit/harness/test_plan_links.py -q`
- `uv run mkdocs build --strict --site-dir /tmp/kaleta-site-check`
- A unit test feeds `check_doc_links.py` a fixture with a broken image link and expects an
  error naming the file and line, and a fixture with a working image link and expects no
  error.
- A unit test runs the archiver's link rewrite on a plan fixture with
  `![x](../../images/a.svg)` and `![y](b.svg)`. It expects `../../images/a.svg`, and
  `../b.svg` when `b.svg` sits in `docs/plans/`.
- After the merge, the "Deploy Pages" workflow on `main` is green.

## Touchpoints
- `scripts/plan_archive.sh` (the inline Python link rewrite).
- `scripts/check_doc_links.py` (`MARKDOWN_LINK` and the link walk).
- `docs/plans/archive/import-api-endpoint.md`,
  `docs/plans/archive/import-mbank-transfer-account-suffix.md`,
  `docs/plans/archive/import-pipeline-service.md` (protected; maintainer session).
- `tests/unit/harness/test_doc_links.py`, `tests/unit/harness/test_plan_links.py` (new). Script
  tests already live in `tests/unit/harness/` (`test_fidelity_*`, `test_seed_defects.py`).

## Open questions
- **Where should the archiver's rewrite be tested if it stays inline Python in a shell
  script?** Default: move the rewrite into a small function the script calls, e.g.
  `scripts/plan_links.py`, so a unit test can import it. Keep the script's behaviour
  otherwise identical.
- **Should the checker also reject an image link to a file outside `docs/`?** mkdocs cannot
  serve it either. Default: yes, the same rule as a `.md` target outside `docs/`. If the
  checker treats `.md` targets differently today, follow that.
- **Does editing the three archived plans need a separate commit?** Default: yes, one commit
  with only those three lines, named "repair image paths in archived plans (frozen history,
  maintainer)", so the history edit is easy to audit.

## Implementation notes

Each open question took its default.
- **The rewrite lives in `scripts/plan_links.py`.** The archiver calls it with
  `python3 scripts/plan_links.py "$plan"`. It is stdlib only, because the archiver and the
  `plan-archive` workflow run it with the system `python3`.
- **Image links outside `docs/`** follow the `.md` rule (below).
- **The three archived plans** are fixed in their own commit, `docs(plans): repair image
  paths in archived plans (frozen history, maintainer)`, and that commit changes only those
  three lines.

### Archiver (`scripts/plan_links.py`, `PlanLinkRewriter`)

- It matches `(!?)\[…\]\(…\)` and keeps the `!`, so an image moves under exactly the rules a
  `[label]` link follows:
  - `../x` becomes `../../x`;
  - `archive/x` becomes `x`;
  - a bare sibling found in `docs/plans/` becomes `../x`;
  - a bare sibling already in `archive/` is unchanged;
  - external links, anchors and unknown targets are left as they are.
- The `roadmap_ref:` frontmatter rewrite moved with it. Behaviour is otherwise identical to
  the old inline block, except that `tel:` and `data:` are also skipped, which can never be
  relative targets anyway.
- The inbound-link block in `plan_archive.sh` (links *to* the moved plan from other docs)
  still matches only `[label]` links. An image cannot point at a plan's `.md`, so it needs
  no change.

### Checker (`scripts/check_doc_links.py`)

- **Image links:** `MARKDOWN_LINK` matches `!?\[…\]\(…\)`. On `main` that surfaced exactly
  the three broken archive paths, the same three warnings `mkdocs --strict` gave.
- **Code is skipped:** with images matched, the check also flagged pattern examples quoted
  in inline code, e.g. in this plan. Markdown does not render a link inside code, and
  mkdocs does not check one. So `prose_lines()` now drops fenced blocks and blanks inline
  code spans before matching. Comparing the old regex with and without this skipping
  showed that no previously checked link is lost.
- **Coverage gap (scope item 5):** mkdocs warns, which fails `--strict`, on a link to a
  file that is not a documentation file. The checker accepted any in-repo target.
  - A page under `docs/` that links a **file** outside `docs/` is now an error
    ("points at a file outside docs/, which mkdocs cannot serve").
  - Directory links outside `docs/` stay allowed: mkdocs only reports them at INFO, which
    is out of scope here. The two that exist today are `deploy-k3s.md` → `../deploy/k3s/`
    and `deployment.md` → `../deploy/supabase/templates/`.
  - Root files (`README.md` and the others in `EXTRA_FILES`) keep linking anywhere in the
    repo, since mkdocs does not build them.
  - Heading anchors are reported at INFO by mkdocs by default, so they are no gap.

### What is *not* this plan's diff

- **The five files under `docs/harness/calibration/`**: `36ef5368e55e44a3-calib.{json,md}`,
  `613e8b9ab733ffd9-calib.{json,md}` and `calib.cases.jsonl`.
  - They are the 2026-11-16 critic-calibration output, which sat untracked in the checkout.
    Committing them is step 1 of plan `critic-calibration-coverage`, so they stay out of this
    PR deliberately.
  - The harness counts untracked files as part of the change (`gitutil.full_diff`), so the
    first critic runs saw them.
  - They were moved out of the working tree with `git stash push -u` ("calibration
    2026-11-16 (critic-calibration-coverage step 1)"), not deleted. Plan
    `critic-calibration-coverage` restores them with `git stash pop`.
- **`docs/plans/README.md`:** its one changed line is this plan's own row in the "Harness"
  index table under "Plans index" (row 9). It came in with the plan file in
  `docs(plans): archive-image-links`, the way the other plans in that table were listed.
  `plan_archive.sh` updates that row on archive. It changes no other plan.

### Results

- `uv run python scripts/check_doc_links.py` gives "OK: all relative links and anchors
  resolve".
- `mkdocs build --strict` builds with no warning; before the repair it aborted with 3.
- The tests in `tests/unit/harness/test_doc_links.py` and `test_plan_links.py` (12)
  include the two required by the acceptance criteria:
  - a broken image link is an error naming `file:line`, and a working one passes;
  - `![x](../../images/a.svg)` becomes `../../images/a.svg`, and `![y](b.svg)` becomes
    `../b.svg` with `b.svg` in `docs/plans/`.
- "Deploy Pages" green after the merge can only be checked on `main`.

## Implementation

Landed on 2026-11-17 (PR #455).

| SHA | Author | Date | Message |
|---|---|---|---|
| `08ca01ec` | Dawid Adamski | 2026-11-17 | Merge pull request #455 from DawidAdamski/plan/archive-image-links |

**Files changed:**
- docs/plans/README.md
- docs/plans/archive-image-links.md
- docs/plans/archive/import-api-endpoint.md
- docs/plans/archive/import-mbank-transfer-account-suffix.md
- docs/plans/archive/import-pipeline-service.md
- scripts/check_doc_links.py
- scripts/plan_archive.sh
- scripts/plan_links.py
- tests/unit/harness/test_doc_links.py
- tests/unit/harness/test_plan_links.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |
