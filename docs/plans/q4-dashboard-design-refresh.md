---
plan_id: q4-dashboard-design-refresh
title: Dashboard design refresh — match the target mockup
area: dashboard
effort: medium
status: draft
roadmap_ref: ../roadmap.md#q4-2026-open-source-launch
---

# Dashboard design refresh — match the target mockup

## Intent

The AI-generated dashboard mockup (`docs/design/dashboard-target.png`)
looks better than the current product — the owner wants the product
to close that gap. This plan treats the mockup as the visual spec for
the dashboard and the shared theme, so the README screenshot can
eventually be a real capture that looks this good.

## Scope

- **Gap analysis first** (recorded in implementation notes before any
  code): side-by-side comparison of the mockup vs the current
  dashboard on seed data — background/surface palette, card corner
  radius and borders, spacing scale, typography (sizes/weights of
  section labels vs values), chart styling (grid lines, series
  colors, legend), sidebar section grouping and iconography, KPI card
  composition (icon chip + label + value).
- **Implement via theme tokens, not per-view styles:** changes land
  in `views/theme.py` (and `chart_utils.py` for ECharts) so every
  page inherits them; per-widget tweaks only where composition
  differs (e.g. KPI icon chip).
- Respect existing rules from `docs/architecture.md` UI Colour
  Schema: semantic colors stay (income green, expense red, transfer
  neutral); every background carries a `dark:` variant; no bare
  Quasar palette classes.
- Light mode must not regress — the mockup is dark-mode; derive the
  light equivalents from the same token changes.
- After the dashboard: apply the same tokens to the remaining pages
  in one sweep (they share components, so most of it is free).
- **Not in scope:** layout/IA changes (widget set and placement stay
  as-is), new widgets, the `ux-audit-feature-categorization` draft
  (separate concern), README screenshot update (manual, after).

## Acceptance criteria

- `./scripts/verify.sh --e2e` green (views change → rule 8).
- No new entries in import-linter ignores; no view file exceeds
  500 LOC.
- `grep -rn "bg-grey-\|text-grey-" src/kaleta/views/` → 0 hits
  (no bare Quasar palette classes introduced).
- `[manual]` Side-by-side: current dashboard vs
  `docs/design/dashboard-target.png` — owner accepts the match.
- `[manual]` Light mode reviewed on dashboard + transactions +
  settings; no unreadable combinations.

## Touchpoints

`src/kaleta/views/theme.py`, `views/chart_utils.py`,
`views/dashboard_widgets/*` (helpers.py primarily),
`views/components/*`, `views/layout.py` (sidebar),
`docs/architecture.md` UI Colour Schema table (update tokens),
`docs/design/dashboard-target.png` (moved from docs/images mockup).

## Open questions

- Font: the mockup appears to use a tighter/different typeface —
  stay on the current stack or add a self-hosted webfont? (Licence
  matters for AGPL distribution; prefer a libre font like Inter.)
- Should the `ux-designer` agent review the gap analysis before
  implementation? (Suggest: yes — cheap second opinion.)

## Implementation notes

(filled in as work progresses)
