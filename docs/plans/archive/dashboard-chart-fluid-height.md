---
plan_id: dashboard-chart-fluid-height
title: Dashboard — Chart widgets honour grid row span
area: dashboard
effort: small
roadmap_ref: ../../roadmap.md#dashboard
status: archived
---

# Dashboard — Chart widgets honour grid row span

## Intent

Chart widgets declared multi-row grid spans but used fixed
`h-XX` Tailwind heights, so resize had no visible effect.

## Scope

(Full scope preserved from draft — see git history.)

## Closed

**2026-07-05** — Folded into `q3-views-refactor` deferred
cosmetic scope. Dashboard widgets were split per-widget during
the refactor; fluid chart height is follow-up polish.

## Implementation notes

Not implemented as a separate unit of work.
