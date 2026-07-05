---
plan_id: settings-panel-color-fix
title: Settings — fix panel colours in light and dark mode
area: settings
effort: small
roadmap_ref: ../../roadmap.md#settings
status: archived
---

# Settings — fix panel colours in light and dark mode

## Intent

Every other surface in the app uses the dark-aware
`SECTION_CARD` / `TOOLBAR_CARD` tokens from
`src/kaleta/views/theme.py`. The Settings page used raw
`ui.card().classes("p-6 …")` everywhere, so panels were
inconsistent in dark mode.

## Scope

(Full scope preserved from draft — see git history.)

## Closed

**2026-07-05** — Folded into `q3-views-refactor` deferred
cosmetic scope. Settings was split into `views/settings/` during
the refactor; surface-token alignment is follow-up polish, not a
standalone plan.

## Implementation notes

Not implemented as a separate unit of work. Track under views-refactor
cosmetic hygiene or Q4 polish.
