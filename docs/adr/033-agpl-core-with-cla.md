---
adr_id: "033"
title: "AGPL-3.0 Core with CLA and Proprietary Commercial Tier"
status: accepted
---

# ADR-33: AGPL-3.0 Core with CLA and Proprietary Commercial Tier

- **Decision**: License the Kaleta core under **GNU Affero General Public License
  v3.0 or later (AGPL-3.0-or-later)**. Require every external contributor to
  sign an **individual Contributor License Agreement (CLA)** before their first
  pull request is merged. Ship **commercial modules under a separate proprietary
  licence** outside this repository (or in a clearly separated proprietary-licensed
  directory), following the open-core model used by Baserow and Grafana.
- **Alternatives considered**:
  - **MIT** — maximises adoption and minimises friction, but allows anyone to
    resell Kaleta as a hosted SaaS without contributing improvements back.
  - **Sustainable-use / n8n-style licence** — restricts commercial hosting while
    staying permissive for most users, but is not OSI-approved and weakens the
    credible "open source" claim.
- **Rationale**: Kaleta targets a self-hosted personal-finance audience while
  preserving a path to a commercial tier. AGPL closes the "SaaS loophole" that
  permissive licences leave open: network use of a modified version triggers the
  copyleft obligation. AGPL is OSI-approved, so the core can honestly be called
  open source. The CLA grants the maintainer the right to dual-license
  contributor code under the proprietary commercial licence without asking each
  contributor again.
- **Consequence**: `LICENSE` carries the verbatim AGPL-3.0 text; every `.py` file
  under `src/`, `tests/`, and `scripts/` carries an SPDX header; `pyproject.toml`
  declares `AGPL-3.0-or-later`. A CLA gate (`.github/workflows/cla.yml`) blocks
  merge until the author signs; signatures live on the `cla-signatures` branch
  at `.cla/signatures.json`. Commercial modules are out of scope for this repo
  until a separate packaging decision is made. Lawyer review of `LICENSE` and
  `docs/cla.md` is tracked as a manual pre-publication step.
