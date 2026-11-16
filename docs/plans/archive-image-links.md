---
plan_id: archive-image-links
title: Image links survive plan archiving; the local link check and verify catch what mkdocs --strict catches
area: docs, harness
effort: small
status: draft
harness: true
roadmap_ref: ../roadmap.md
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
  links. A `![alt](../x)` target becomes `![alt](../../x)` under the same rules as `[label]`
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
  `![x](../images/a.svg)` and `![y](b.svg)`. It expects `../../images/a.svg`, and
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
