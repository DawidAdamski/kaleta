---
plan_id: q4-licence-and-cla
title: Licence — AGPL-3.0 core + CLA, decision record and tooling
area: infrastructure
effort: medium
status: done
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Licence — AGPL-3.0 core + CLA, decision record and tooling

## Intent

Decision made 2026-07-05: **AGPL-3.0-or-later for the core, individual
CLA for contributors, commercial modules under a separate proprietary
licence** (Baserow/Grafana model). AGPL prevents a third party from
reselling Kaleta as a hosted SaaS without contributing back; the CLA
preserves the right to dual-license contributor code for the
commercial tier. This plan lands the decision as an ADR, the LICENSE
file, per-file SPDX headers, and CLA automation — the blocking
prerequisite for making the repo public.

## Scope

- **ADR-033** (`docs/adr/033-agpl-core-with-cla.md`): decision,
  alternatives considered (MIT, sustainable-use/n8n-style), rationale
  (open-core commercial model, SaaS-resale protection, OSI-approved
  licence for credible "open source" claim), consequences (CLA
  required before first external PR; commercial modules live outside
  this repo or in a clearly separated proprietary-licensed directory).
- `LICENSE` — full AGPL-3.0 text (verbatim from gnu.org).
- `pyproject.toml` — `license = "AGPL-3.0-or-later"` (SPDX expression)
  and classifier.
- SPDX headers: one-line
  `# SPDX-License-Identifier: AGPL-3.0-or-later` at the top of every
  `.py` file under `src/` (scripted, idempotent; add a check to
  verify.sh or CI so new files can't omit it).
- CLA:
  - `docs/cla.md` — individual CLA text (Apache ICLA-derived, adapted:
    contributor grants copyright licence + patent licence, allows
    relicensing by the maintainer).
  - CLA gate via the `contributor-assistant/github-action` workflow
    (`.github/workflows/cla.yml`) — blocks PR merge until the author
    has signed (signatures stored in the repo or a dedicated branch).
- README: licence section + AGPL badge; one paragraph explaining the
  open-core split in plain words.
- **Not in scope:** the commercial modules themselves, lawyer review
  (tracked as a manual criterion), trademark registration.

## Acceptance criteria

- `test -f LICENSE && grep -q "GNU AFFERO GENERAL PUBLIC LICENSE" LICENSE`
- `grep -q 'AGPL-3.0-or-later' pyproject.toml`
- `test -f docs/adr/033-agpl-core-with-cla.md`
- `[ -z "$(grep -rL 'SPDX-License-Identifier: AGPL-3.0-or-later' src/kaleta --include='*.py')" ]`
  (every .py under src/ carries the header)
- `test -f docs/cla.md && test -f .github/workflows/cla.yml`
- `grep -qi "AGPL" README.md`
- `uv run python scripts/check_doc_links.py` passes
- `[manual]` Lawyer review of LICENSE + CLA before the repo is made
  public (one consultation; record date + outcome here).

## Touchpoints

`LICENSE` (new), `docs/adr/033-*.md` (new), `docs/cla.md` (new),
`.github/workflows/cla.yml` (new), `pyproject.toml`, `README.md`,
all `src/kaleta/**/*.py` (header line), `scripts/` (SPDX check),
`docs/architecture.md` (ADR index).

## Open questions

- SPDX headers also on `tests/` and `scripts/`? **Resolved: yes** — same
  `AGPL-3.0-or-later` header on every `.py` under `src/kaleta`, `tests/`,
  and `scripts/`; enforced by `scripts/check_spdx_headers.py`.
- Signature storage for CLA action: **Resolved: in-repo `cla-signatures`
  branch** at `.cla/signatures.json` (no separate repository).

## Implementation notes

- 2026-07-05: ADR-033, verbatim `LICENSE` from gnu.org, `pyproject.toml`
  SPDX expression + classifier, SPDX headers on 302 Python files,
  `docs/cla.md` (Apache ICLA-derived), `.github/workflows/cla.yml`
  (contributor-assistant/github-action@v2.6.1), README licence section
  with AGPL badge and open-core paragraph.
- Maintainer must create an unprotected `cla-signatures` branch before the
  CLA workflow can persist signatures (the action creates
  `.cla/signatures.json` on first sign).
- `[manual]` Lawyer review of LICENSE + CLA — left unchecked for owner.
