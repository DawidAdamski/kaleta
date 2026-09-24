---
plan_id: deps-upgrade-2026-09
title: Dependencies — relock everything to latest within current constraints (2026-09)
area: cross-cutting
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#cross-cutting-principles
---

# Dependencies — relock everything to latest within current constraints (2026-09)

## Intent

`uv lock --upgrade --dry-run` on 2026-09-24 reports 71 packages behind
(plus two removals) — nothing is held back by `pyproject.toml`, the lock
simply has not been refreshed since the bandit removal. Staying current
in small, regular steps is cheaper than one big jump later, and the dev
tools (ruff, mypy, import-linter) drive what CI and pre-commit enforce.

Notable moves in the dry-run:

| Package | From → to | Why it matters |
|---|---|---|
| nicegui | 3.14.0 → 3.17.1 | the whole UI; drops `lxml` / `lxml-html-clean` |
| starlette / fastapi / uvicorn | 1.3.1 → 1.7.0 / 0.139 → 0.141 / 0.49 → 0.53 | request stack under NiceGUI and the API |
| websockets | 16.0 → 17.1 (major) | NiceGUI's socket transport |
| python-socketio / engineio | 5.16 → 5.17 / 4.13 → 4.14 | same |
| sqlalchemy / alembic | 2.0.51 → 2.0.54 / 1.18 → 1.20 | ORM and migrations |
| ruff | 0.15.20 → 0.16.8 (minor with new rules) | lint/format gate |
| mypy | 2.1.0 → 2.3.1 | strict type gate |
| import-linter | 2.13 → 2.15 | architecture contracts |
| playwright / pytest-playwright | 1.61 → 1.63 / 0.8 → 0.9 | e2e; needs a browser reinstall |
| prophet | 1.3.0 → 1.4.0 | optional forecast extra |
| filelock | 3.29 → 4.0 (major) | transitive only |

## Scope

- `uv lock --upgrade` for every package, then `uv sync --group dev`.
- Fix whatever the new versions break: new ruff rules or format
  changes, new mypy findings, API changes in NiceGUI / Starlette /
  SQLAlchemy / pydantic, e2e selector drift from NiceGUI markup changes.
  Every fix states which upgrade caused it.
- Tool-driven repo-wide changes (e.g. `ruff format` output) go in their
  own commit, separate from the lock and from code fixes (Working
  Agreement §9).

Out of scope:
- Raising version floors in `pyproject.toml`, unless a fix *needs* a
  newer API — then raise only that floor, with the reason.
- Adding or removing direct dependencies.
- Python version changes, container base images, GitHub Actions
  versions.
- Adopting new features of the upgraded libraries.

## Acceptance criteria

- `uv lock --check`
- `grep -A1 'name = "nicegui"' uv.lock | grep -q 'version = "3.17'`
- `grep -A1 'name = "ruff"' uv.lock | grep -q 'version = "0.16'`
- `grep -A1 'name = "mypy"' uv.lock | grep -q 'version = "2.3'`
- `./scripts/verify.sh --e2e`

## Touchpoints

`uv.lock`; anything the upgraded tools or libraries flag.

## Open questions

- If one package's upgrade breaks something that cannot be fixed within
  this scope: hold that one package back (`uv lock --upgrade` then
  `uv lock --upgrade-package <pkg>==<old>`) and record why here, rather
  than stalling the whole relock. Default: hold back, note it, file a
  chore.
- Raise floors to the new versions? Default: no (see Out of scope).

## Implementation notes
