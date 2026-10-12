---
plan_id: auto-versioning
title: Automatic version numbers — every build and release traceable to a commit
area: build / ci / observability
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md
---

# Automatic version numbers — every build and release traceable to a commit

## Intent

Today the version is hard-coded (`version = "0.1.0"` in `pyproject.toml`,
`__version__ = "0.1.0"` in `src/kaleta/__init__.py`) and never changes, so the
version already shown in `/api/v1/health`, the debug panel, logs, bug reports and
app events is meaningless — every deploy says `0.1.0`. There are no git tags and
no release numbers. We want an **automatic** version: a number nobody types by
hand, that rises with the work merged, and that lets anyone later point at a
running instance and say exactly which commit it is.

## What exists (2026-10-12)

- `app_version()` (`observability/version.py`) reads the installed package version
  via `importlib.metadata`; falls back to `"unknown"` outside an installed tree.
- The version is surfaced already: `api/v1/health.py` (`version=snapshot.version`),
  `debug_info.py` ("Kaleta", app_version()), `logging_config.py` (every log line),
  `models/bug_report.py` and `models/app_event.py` (`app_version` column, String(40)).
- Build backend is `hatchling`; `version` is static in `[project]`.
- Conventional-commit messages are already the norm (`feat(...)`, `fix(...)`,
  `docs(...)`), which is what a release tool needs to compute the next number.
- CI: `.github/workflows/{ci,docker,pages,pr-review,plan-archive,cla}.yml`. No tags,
  no releases, no changelog.

## Scope

- **Version derived from git, not hard-coded.** Replace the static `version` with a
  VCS-derived one (`hatch-vcs`): the package version comes from the latest `vX.Y.Z`
  tag, and an untagged build between tags is `X.Y.(Z+1).devN+g<shortsha>` — so a dev
  or CI build is still a unique, traceable string, not `0.1.0`. `src/kaleta/__init__.py`
  stops hard-coding `__version__` and reads it from `importlib.metadata`
  (single source of truth; `app_version()` already does this).
- **Release numbers computed from commits, cut by merging a PR.** Add
  `release-please` (GitHub Action) on `main`: it reads conventional commits since the
  last release and keeps an open "release PR" that bumps the number and updates
  `CHANGELOG.md`. Merging that PR creates the `vX.Y.Z` git tag and a GitHub Release.
  The maintainer never types the number — they approve it — which fits the
  merge-driven workflow. `feat:` → minor, `fix:` → patch, `feat!:`/`BREAKING CHANGE`
  → major (pre-1.0 handling recorded in Implementation notes).
- **Docker images tagged with the version and the sha.** `docker.yml` tags the image
  with the release version (on a tag build) and always with the short commit sha, and
  passes the version into the build so the running container reports it (build arg →
  env → `app_version()` fallback when git metadata is absent in the image). A deployed
  container is then traceable to a commit — the hook the `deploy-k3s` plan needs.
- **The version is visible and verified.** `/api/v1/health` returns the real version;
  a test asserts it is no longer the literal `0.1.0` and matches the expected shape.
- BDD: `KAL-OPS-*` for "the running app reports a real, commit-traceable version".

## Not in scope

- The k3s rollout itself (`deploy-k3s`) — this plan only makes the image carry a
  traceable version/tag.
- Back-tagging history or inventing past releases; the first tag this introduces is
  the baseline.
- Publishing to PyPI or a package registry (open-core packaging is a later question).
- Signed releases / SBOM (a `security-assessment` follow-up may add them).

## Acceptance criteria

- `uv run python -c "import kaleta; assert kaleta.__version__ and kaleta.__version__ != '0.1.0'"`
- `test -f CHANGELOG.md`
- `test -f .github/workflows/release-please.yml`
- `grep -q "hatch-vcs" pyproject.toml`
- `uv run pytest tests/integration/test_health.py -q`
- `uv run pytest tests/unit/observability/test_version.py -q`
- `./scripts/verify.sh`

## Touchpoints

`pyproject.toml` (dynamic version, `hatch-vcs`), `src/kaleta/__init__.py`,
`src/kaleta/observability/version.py` (dev-build fallback via build-arg env),
`.github/workflows/release-please.yml` (new), `.github/workflows/docker.yml`
(version + sha tags, build arg), `CHANGELOG.md` (new, release-please owned),
`tests/integration/test_health.py`, `tests/unit/observability/test_version.py` (new),
`docs/bdd.md`, `docs/tech-stack.md` (document the scheme).

## Open questions

- **Release tool: `release-please` vs `python-semantic-release`.** Default:
  `release-please` — its release-PR model means the number is computed automatically
  but a human approves the cut by merging, matching how this repo already works
  (every change lands by merging a PR). `python-semantic-release` tags on every push
  to `main` (more automatic, less control, noisier history). Decide on first
  implementation; record why.
- **Pre-1.0 bumping.** Default: stay `0.x` and let `feat:` bump the minor, `fix:` the
  patch, until the app is declared 1.0; configure release-please's
  `bump-minor-pre-major`/`bump-patch-for-minor-pre-major` accordingly.
- **Version string in an image built without `.git`.** Default: pass the version as a
  Docker build arg (from the Action's computed value) into an env var that
  `app_version()` prefers over `importlib.metadata`, so a squashed image still reports
  correctly. Confirm the precedence order during implementation.
- **`String(40)` width** for `bug_report.app_version` / `app_event.app_version`: a dev
  version like `0.2.1.dev14+g8b57246` fits, but confirm the longest plausible string
  stays under 40, else widen in the same migration.

## Implementation notes

### Delivery in two PRs

- **Part 1 — the git-derived version (this PR)**: `hatch-vcs` computes the version from
  git tags and bakes it into the installed package (and a generated, git-ignored
  `src/kaleta/_version.py`); `src/kaleta/__init__.py` resolves it from package metadata
  (fallback `"0.0.0+unknown"` when not installed); `app_version()` delegates to it, so
  there is one source of truth. No repo settings, no CI, no release tool — it works the
  moment the dependency is synced, and needs nothing from the maintainer.
- **Part 2 — release automation (next PR)**: `release-please` on `main` cuts `vX.Y.Z`
  tags/releases from conventional commits, and `docker.yml` tags images with the version
  and sha and bakes the version in via a build arg (`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_KALETA`,
  since the image build has no `.git`). CI/build jobs that need an accurate version add
  `fetch-depth: 0` to their checkout (a shallow clone has no tags; Part 1 tolerates this
  via the fallback, Part 2 needs the real tag). Part 2 needs the maintainer to enable
  *Settings → Actions → General → "Allow GitHub Actions to create and approve pull
  requests"* and to confirm `release-please` over `python-semantic-release`.

### Decisions (Part 1)

- **No tag yet → `0.0.1.devN+g<sha>`.** With no `vX.Y.Z` tag, setuptools_scm (under
  hatch-vcs) guesses the next patch and marks it a dev build with the commit sha, e.g.
  `0.0.1.dev1087+g12fc655` (plus a `.dYYYYMMDD` suffix only when the working tree is
  dirty). Unique per commit, so every build is traceable even before the first release.
  Part 2's first release PR sets a real baseline tag.
- **`tag_regex` pins `v`-prefixed tags** so only `vX.Y.Z` drives the version (not an
  unrelated tag someone pushes).
- **`fallback-version = "0.0.0"`** keeps a source tarball without `.git` buildable (a
  wheel built from a git-less copy reports `0.0.0`, confirmed), so the Docker image build
  cannot fail; Part 2 gives it the real version through a build arg
  (`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_KALETA`). The build hook writes
  `src/kaleta/_version.py` as an embedded artifact; nothing imports it today — the app
  reads the version from package metadata — it is kept for Part 2 to consume if it wants a
  no-metadata fallback.
- **Editable-install staleness**: `importlib.metadata` fixes the version at `uv sync`
  time, so a local dev tree lags new commits (and shows a `.dYYYYMMDD` dirty suffix) until
  reinstalled. Inherent and fine for the build/Docker case; tests do not depend on it.
- **`String(40)` is enough** (open question resolved): the longest realistic string,
  `0.0.1.dev9999+g12345678.d20261012` (~33 chars), fits; no migration needed.
- **Single source of truth**: `kaleta.__version__` is the only resolver; `app_version()`,
  health, logs, debug panel and events all read through it. `main.py` now gives FastAPI
  `app_version()` instead of a hard-coded `"0.1.0"`, so the OpenAPI document reports the
  real version too.
- **The UI displays need no change**: the drawer foot (`views/layout.py`) and the login
  foot (`views/auth_common.py`) already read the version from package metadata and only
  fell back to `"v0.1.0"` in a non-installed source checkout; with the version now
  git-derived they show the real one. Left untouched so Part 1 stays off the view layer
  (no e2e gate); a later cleanup can point them at the single resolver.
