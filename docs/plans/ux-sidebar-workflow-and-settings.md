---
plan_id: ux-sidebar-workflow-and-settings
title: Sidebar redesign around workflows + settings expansion
area: ux
effort: medium
status: draft
deferred_to: q4-2026
roadmap_ref: ../roadmap.md#ux
---

# Sidebar redesign around workflows + settings expansion

## Intent

Two related UX debts. (1) The left nav groups pages by *what they are*
(`nav.group_overview`, `nav.group_manage`, …) rather than by *when the
user needs them* — daily capture, the monthly cycle, the yearly ritual,
ongoing insight. The BDD spec is now organised around exactly those
workflows (`docs/bdd.md` workflow map); the nav should mirror it, and
the visual density/appearance needs a pass. (2) Settings expose only a
fraction of what users reasonably expect to control.

**Spec first:** before implementation, add `@planned` scenarios to
`docs/bdd.md` (new features: Navigation — KAL-NAV; extend Settings —
KAL-SET range) and a GitHub issue per PR below. Do not start from this
plan alone.

## Scope

### PR 1 — sidebar (`views/layout.py`)

- Regroup nav to mirror the workflow map in `docs/bdd.md`:
  - **Capture** (daily/weekly): Transactions, Import
  - **Monthly**: Budgets, Budget Plan, Monthly Readiness,
    Payment Calendar, Subscriptions
  - **Yearly & funds**: Yearly Plan, Safety Funds, Personal Loans
  - **Insight**: Dashboard, Reports, Net Worth, Forecast, Credit
  - **Setup** (rarely): Accounts, Institutions, Categories, Tags,
    Payees — collapsed by default
- Collapsible groups; expanded/collapsed state persisted per user
  (storage consistent with existing UI-state persistence).
- Mini mode (icons only) toggle; active-page highlight; spacing and
  icon pass. Wizard entry stays prominent (top, outside groups).
- i18n: new `nav.group_*` keys in `en.json` + `pl.json`.
- e2e smoke: every nav item still routes (guards the regroup).
- [manual] `ux-designer` subagent review against Nielsen heuristics
  before merge.

### PR 2 — settings expansion (`views/settings/`)

- **General tab**: default currency, date/number format, first day of
  week, budget month start day, default account for quick entry.
- **Features tab** (extends the existing `features_tab.py`): detection
  thresholds — transfer pairing window (days) and amount tolerance,
  subscription detector sensitivity, payee dedupe sensitivity; import
  defaults (duplicate skip on/off). Wire each to the service that
  currently hardcodes the value (e.g. `import_service`
  `max_days_apart=3`, `amount_tolerance=0.01`).
- **Privacy & diagnostics tab** (new): telemetry/event capture toggle,
  event retention days, "copy session ID" button — the UI surface for
  [`observability-anonymous-events`](observability-anonymous-events.md).
- Settings model: reuse the existing settings persistence; every new
  option needs a sane default and must work with no user action.

Out of scope:
- Dashboard widget redesign (`q4-dashboard-design-refresh` covers it).
- Multi-user settings inheritance (2027 workspaces).
- The telemetry backend itself (plan `observability-anonymous-events`).

## Acceptance criteria

- `grep -qE "KAL-NAV-[0-9]{3}" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `bash scripts/verify.sh`
- [manual] Nav groups match the bdd.md workflow map; collapsed state
  survives reload; mini mode usable; new settings all have defaults
  and take effect without restart.
