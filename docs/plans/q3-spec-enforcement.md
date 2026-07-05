---
plan_id: q3-spec-enforcement
title: Spec enforcement — make architecture, BDD, and plans machine-verifiable
area: infrastructure
effort: medium
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Spec enforcement — make architecture, BDD, and plans machine-verifiable

## Intent

Kaleta's spec loop (roadmap → plans → ADRs → BDD → archive) is
structurally sound but nothing detects drift between spec and code.
Proof: `controllers/` stayed empty for 75 commits while
`architecture.md` declared it; `docs/bdd.md` has 115 scenarios but only
5 e2e test files, with no mapping between them; `roadmap_ref` anchors
break silently. This plan turns the specs from prose into checks that
fail CI.

## Scope

### 1. Architecture as code (import-linter)

- Add `import-linter` as a dev dependency with contracts in
  `pyproject.toml`:
  - layers contract: `views` → `services` → `models` (a lower layer
    never imports a higher one);
  - forbidden: `kaleta.views` importing `kaleta.models`, `kaleta.db`,
    or `sqlalchemy` directly (data access only via services);
  - forbidden: `kaleta.services` importing `kaleta.views` or `nicegui`;
  - forbidden: `kaleta.api` importing `kaleta.views`.
- Run `lint-imports` in the CI lint job (extends the workflow from
  `q3-engineering-hygiene`).
- Existing violations found on first run: fix trivial ones inline;
  register genuinely hard ones as explicit `ignore_imports` entries
  with a `# TODO(q3-views-refactor)` note — the refactor plan burns
  them down; the ignore list must only ever shrink.

### 2. BDD scenario IDs + coverage report

- Assign stable IDs to every scenario in `docs/bdd.md`:
  `KAL-<AREA>-<NNN>` (e.g. `KAL-TXN-003`), as a tag line above each
  `Scenario:`. Tag each as `@automated` or `@manual`.
- Every test in `tests/e2e/` declares the scenario ID(s) it covers in
  its docstring (`Covers: KAL-TXN-003`).
- New script `scripts/spec_coverage.py`:
  - parses `docs/bdd.md` → set of scenario IDs + tags;
  - parses `tests/e2e/` docstrings → set of covered IDs;
  - fails (exit 1) if any `@automated` scenario has no test, if a test
    references an unknown ID, or if IDs are duplicated;
  - prints a coverage summary table (per Feature: automated / manual /
    uncovered).
- Run in CI; summary posted in job output.
- Retro-tag the 5 existing e2e files and the 5 flows from
  `q3-test-safety-net`.

### 3. Executable acceptance criteria in plans

- Extend the plan template in `docs/plans/README.md`: acceptance
  criteria SHOULD be written as verifiable commands (pytest
  invocation, grep with expected count, coverage threshold) wherever
  possible; prose only where a human judgement is inherent (visual
  checks), marked `[manual]`.
- Extend the `plan-archiver` subagent definition: before archiving,
  it extracts commands from `## Acceptance criteria` and runs them;
  archive is blocked on failure, and the run result is recorded in
  the `## Implementation` section.

### 4. Reference integrity

- Add a docs link-checker to CI (e.g. `lychee` offline mode or a
  small script): all relative links and anchors in `docs/**/*.md`,
  `README.md`, `CLAUDE.md` must resolve. Fixes the silent
  `roadmap_ref` anchor breakage.

### 5. ADR housekeeping (small, do last)

- Split `architecture.md` ADR section into `docs/adr/NNN-slug.md`,
  one file per ADR, frontmatter `status: accepted | superseded-by:
  NNN`. Keep numbering; fix the out-of-order placement (021, 030/031).
  `architecture.md` keeps the diagram + an index table of ADRs.
- Update `CLAUDE.md` key-documents section and mkdocs nav.

**Not in scope:** pytest-bdd migration (scenario-ID mapping is
sufficient), README feature-list generation (Q4 candidate), coverage
gates on unit tests.

## Acceptance criteria

- `uv run lint-imports` passes in CI; contract file exists in
  `pyproject.toml`; ignore list documented with TODO markers.
- `grep -c "KAL-" docs/bdd.md` ≥ 115 (every scenario tagged);
  `uv run python scripts/spec_coverage.py` exits 0 and lists 0
  uncovered `@automated` scenarios.
- Link-checker passes on `docs/`, `README.md`, `CLAUDE.md`.
- `docs/adr/` contains one file per ADR incl. ADR-032; old inline
  section replaced by an index; mkdocs build passes.
- Plan template updated; `plan-archiver` agent definition updated.
- ruff + mypy strict pass; no production code behaviour changes.

## Touchpoints

`pyproject.toml` (import-linter config + dev dep), `docs/bdd.md`
(IDs/tags), `tests/e2e/*` (docstrings), `scripts/spec_coverage.py`
(new), `.github/workflows/ci.yml`, `docs/plans/README.md` (template),
plan-archiver agent definition (`.claude/` or `.ai/`), `docs/adr/`
(new), `docs/architecture.md`, `CLAUDE.md`, `mkdocs.yml`.

## Open questions

- Where does the plan-archiver agent definition live (`.claude/agents/`
  vs `.ai/`)? Locate and update the actual file.
- Link-checker tool: `lychee` binary in CI vs pure-python script?
  (Prefer whatever needs no extra toolchain — a ~50-line python
  script over the existing test infra is fine.)
- Should `spec_coverage.py` also check that every plan's
  `roadmap_ref` anchor resolves, or leave that to the link-checker?
  (Leave to link-checker if it handles anchors.)

## Implementation notes

- Sections 1–2 (import-linter, BDD coverage) were done before this
  tranche.
- **Section 3:** Plan template in `docs/plans/README.md` now requires
  backtick-wrapped shell commands in acceptance criteria; `[manual]`
  prefix for prose checks. `plan-archiver` runs commands before archive
  and records results in `## Implementation`.
- **Section 4:** `scripts/check_doc_links.py` validates markdown links,
  `roadmap_ref` frontmatter, and heading anchors in `docs/`, `README.md`,
  `CLAUDE.md`. CI lint job + `verify.sh`. Fixed archived plan relative
  paths and added stable `roadmap_ref` anchors to `docs/roadmap.md`.
- **Section 5:** 32 ADRs split to `docs/adr/NNN-slug.md`; index table
  in `architecture.md`; mkdocs nav updated; diagram aligned with
  ADR-032 (no controller layer).
