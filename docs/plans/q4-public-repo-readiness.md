---
plan_id: q4-public-repo-readiness
title: Public-repo readiness — contributor docs, security policy, templates
area: infrastructure
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Public-repo readiness — contributor docs, security policy, templates

## Intent

Everything a stranger needs to trust and contribute to Kaleta on day
one of the repo being public. Pre-publication audit (2026-07-05)
found the repo clean (no secrets in history, no tracked databases);
what is missing is the standard OSS scaffolding.

**Blocked by:** `q4-licence-and-cla` — CONTRIBUTING references the
CLA, and publishing without LICENSE is pointless.

## Scope

- **CONTRIBUTING.md** — distilled from how this repo actually works:
  1. one unit of work = one plan in `docs/plans/` (template in its
     README), 2. the Working Agreement in `AGENTS.md` applies to
  humans and AI agents alike, 3. `uv sync --group dev` +
  `./scripts/verify.sh` must be green before a PR (`--e2e` when
  views change), 4. architecture contracts (import-linter) and BDD
  coverage (`spec_coverage.py`) are CI-enforced, 5. CLA signature
  required on first PR. Short — link to the existing docs instead of
  duplicating them.
- **SECURITY.md** — private vulnerability reporting via GitHub
  Security Advisories; supported-versions table (single `main` line
  for now); pledge on response time (e.g. 14 days). Contact: the
  dedicated project alias (see open questions — must exist before
  the repo flips public; use a `TODO-project-alias` placeholder
  string until then so the link-checker/grep can find it).
- **Code of Conduct: deliberately deferred** (owner decision
  2026-07-05) — revisit when the first external contributors show
  up. Do NOT add CODE_OF_CONDUCT.md in this plan.
- **Issue/PR templates** (`.github/ISSUE_TEMPLATE/bug.yml`,
  `feature.yml`, `config.yml` with `blank_issues_enabled: false` —
  forced forms, owner decision 2026-07-05;
  `.github/pull_request_template.md` with a verify.sh checklist and
  plan reference). GitHub Discussions stay off.
- **README stranger pass:** above-the-fold: what Kaleta is (one
  paragraph), screenshot, quick start (3 commands), licence badge +
  CI badge, links to docs site/CONTRIBUTING/SECURITY. Move
  historical/internal detail into docs/.
- **Docs site:** verify the existing `pages.yml` workflow publishes
  the mkdocs site correctly once public; fix base URL if needed.
- **Not in scope:** hosted demo instance (separate plan when
  infrastructure is chosen), zero-config bootstrap (own draft),
  GitHub repo settings themselves (branch protection — done by hand
  at flip-to-public, checklist in implementation notes).

## Acceptance criteria

- `test -f CONTRIBUTING.md && test -f SECURITY.md && ! test -f CODE_OF_CONDUCT.md`
- `test -f .github/pull_request_template.md && ls .github/ISSUE_TEMPLATE/*.yml | wc -l` ≥ 2
- `grep -q "blank_issues_enabled: false" .github/ISSUE_TEMPLATE/config.yml`
- `grep -q "verify.sh" CONTRIBUTING.md && grep -q "cla" CONTRIBUTING.md -i`
- `grep -qiE "badge|shields" README.md`
- `uv run python scripts/check_doc_links.py` passes (new files included)
- `uv run mkdocs build --strict` passes
- `[manual]` Project security alias created and the
  `TODO-project-alias` placeholder replaced in SECURITY.md — gates
  the flip to public.
- `[manual]` A person who has never seen the repo follows README
  quick start on a clean machine and reaches the login page.
- `[manual]` Flip-to-public checklist recorded in implementation
  notes: branch protection on `main` (require CI green), Security
  Advisories enabled, Discussions off.

## Touchpoints

`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` (new),
`.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` (new),
`README.md`, `mkdocs.yml` / `.github/workflows/pages.yml`.

## Open questions

- Contact e-mail in SECURITY/CoC: firmowy (redpulse.tech) — confirmed
  by owner 2026-07-05.
- Screenshot in README: which view sells best? (Suggest: dashboard in
  dark mode with seed data.)

## Implementation notes

### Owner decisions (2026-07-05)

- **No `CODE_OF_CONDUCT.md`** — deliberately deferred until external
  contributors appear.
- **Issue forms only** — `blank_issues_enabled: false` in
  `.github/ISSUE_TEMPLATE/config.yml`.
- **`SECURITY.md` contact** — literal placeholder `TODO-project-alias`
  until the project security alias exists (owner replaces manually
  before flip to public).

### Delivered in this implementation

- `CONTRIBUTING.md` — links to `AGENTS.md` Working Agreement,
  `docs/plans/README.md`, `verify.sh`, and `docs/cla.md` (no
  duplication).
- `SECURITY.md` — supported-versions table (`main` only), GitHub
  Security Advisories reporting, 14-day response pledge,
  `TODO-project-alias` contact placeholder.
- `.github/ISSUE_TEMPLATE/{bug,feature}.yml` + `config.yml`.
- `.github/pull_request_template.md` with verify.sh checklist and plan
  reference.
- README stranger pass — badges, screenshot (`docs/images/dashboard-dark.png`),
  three-command quick start, links to docs / CONTRIBUTING / SECURITY;
  detailed setup moved to `docs/getting-started.md`.
- `scripts/check_doc_links.py` — `CONTRIBUTING.md` and `SECURITY.md`
  included in link checks.
- `mkdocs.yml` — Getting started page in nav; `pages.yml` workflow
  unchanged (already builds with `--strict`).

### Flip-to-public checklist (manual — owner)

- [ ] Replace `TODO-project-alias` in `SECURITY.md` with the live
  project security alias.
- [ ] Branch protection on `main`: require CI green before merge.
- [ ] GitHub **Security Advisories** enabled (private reporting).
- [ ] GitHub **Discussions** left off.
- [ ] Clean-machine quick start smoke test (README → login page).
