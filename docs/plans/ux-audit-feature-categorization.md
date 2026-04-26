---
plan_id: ux-audit-feature-categorization
title: UX audit — feature categorisation in nav and settings
area: ux
effort: medium
roadmap_ref: ../roadmap.md#ux
status: draft
---

# UX audit — feature categorisation in nav and settings

## Intent

Kaleta has grown to ~25 pages organised under three sidebar
groups (Overview / Manage / Tools / Setup) and a Settings tab
strip (General / Appearance / Features / Data / History /
About). Some assignments feel arbitrary today: e.g. *Credit
Calculator* sits under "Tools" while the *Credit* module sits
next to it; *Tags* and *Payees* live under "Setup" alongside
*Settings*; *Wizard* and *Housekeeping* are bundled with
forecasting and credit; *Payment Calendar* sits in "Manage"
even though it is largely a planning view. This plan
commissions a structured information-architecture review by
the `ux-designer` subagent and translates the findings into
concrete renames / regroupings, executed as a follow-up plan
(or absorbed into existing plans where tiny).

## Scope

**Phase 1 — audit (this plan delivers the document)**

Run the `ux-designer` subagent with the brief:
- inventory every nav item and settings tab, with one-line
  purposes;
- map them to the user's mental model using Kaleta's BDD
  scenarios in `docs/bdd.md` as canonical user goals;
- evaluate the current grouping against Nielsen heuristics
  (especially "Match between system and real world" and
  "Recognition rather than recall");
- propose a re-grouping with rationale per move; for each
  proposed move call out the breakage cost (URL changes,
  i18n key churn, muscle memory).

Deliverable: `docs/ux/feature-categorization-audit.md`,
checked into the repo, with a recommended sidebar tree, a
recommended settings tab list, and a cost-ranked migration
list.

**Phase 2 — implementation (follow-up plan)**

Once the audit lands, spawn one of:
- a tiny "rename / regroup" plan if the cost is low and the
  audit recommends a small shuffle (changes in
  `views/layout.py`, i18n keys, no URL changes); or
- a larger plan if it recommends URL renames or splits
  (`/transactions` → `/transactions/list` etc.) — those
  need redirects, link audits, and BDD test updates.

Out of scope for *this* plan: actually moving things. The
deliverable is the audit document.

## Acceptance criteria

- `docs/ux/feature-categorization-audit.md` exists and:
  - lists all 25+ nav entries with current group + proposed
    group;
  - lists all settings tabs + proposed structure;
  - rationales reference Nielsen heuristics and 1+ BDD
    scenario each;
  - flags every recommendation with breakage cost (low /
    medium / high) and migration notes.
- A short summary section at the top makes it possible for
  a reader to skim the whole audit in 90 seconds.
- The follow-up plan(s) are listed under "Plans index" in
  `docs/plans/README.md` once written.

## Touchpoints

- `docs/ux/feature-categorization-audit.md` — new file
  (this plan creates it).
- Subagent: `ux-designer` for the heuristic + BDD review.
- Reference inputs:
  - `src/kaleta/views/layout.py` (NAV_GROUPS).
  - `src/kaleta/views/settings.py` (tab list).
  - `docs/bdd.md` (user goals).
  - `docs/architecture.md` (capability map).

## Open questions

1. **Should the audit include the Wizard's internal panel
   ordering?** Default: **yes** — the Wizard is itself an
   IA artefact; auditing only the top-level nav misses half
   the surface.
2. **Audit format** — narrative + table, or pure table?
   Default: **table-first**, with prose only where the
   rationale needs it.
3. **Pilot user input** — are there real users to interview?
   Default: **no**, the audit is heuristic-only; a future
   plan can bolt on a usability study.

## Implementation notes
_Filled in as work progresses._
