# Implementation Plans

Active plan files live in this folder. Each plan captures one unit of
work — small enough to ship in one or a few PRs. Completed plans move
to [`archive/`](archive/) with their commit reference appended.

See the [roadmap](../roadmap.md) for the big picture and the
[product docs](../product/index.md) for deep-dives on dashboard and
wizard.

## Lifecycle

```
draft ──► in-progress ──► ready-to-archive ──► archived
```

1. **Draft.** Plan written; not picked up yet.
2. **In-progress.** Implementation started. Status field updated in
   the plan frontmatter.
3. **Ready-to-archive.** Implementation merged. Plan is handed to the
   `plan-archiver` subagent which stamps it with the commit
   reference(s) and moves it to `archive/`.
4. **Archived.** Frozen historical record. Never edited.

## Plan file template

```markdown
---
plan_id: <kebab-slug>
title: <human title>
area: <module — accounts, wizard, dashboard, ...>
effort: small | medium | large
status: draft | in-progress | ready-to-archive | archived
roadmap_ref: ../roadmap.md#<anchor>
---

# <title>

## Intent
One paragraph — user need being solved.

## Scope
Bullet list — what this plan covers and explicitly what it does not.

## Acceptance criteria
Testable outcomes. Reference BDD scenarios if available.

Write criteria as **executable commands** wherever possible — one
backtick-wrapped command per bullet. The `plan-archiver` runs these
before archiving; archive is blocked on failure.

```markdown
## Acceptance criteria

- `uv run pytest tests/unit/services/test_foo.py -q`
- `grep -c "KAL-TXN" docs/bdd.md | grep -qE '^[1-9]'`
- `uv run python scripts/spec_coverage.py`

Prose-only checks (visual review, UX judgement) must start with
`[manual]` — the archiver skips them:

- `[manual]` Dialog uses theme tokens in dark mode.
```

Supported command forms: `uv run …`, `./scripts/…`, `grep …`,
`test …`, `python …`. Do not embed commands in prose paragraphs.

## Touchpoints
Files, models, services, i18n keys, migrations likely to change.

## Open questions
Anything to resolve before starting (or during).

## Implementation notes
Filled in as work progresses.

## Implementation (filled by plan-archiver)
Commit SHAs and short summaries; added when the plan archives.
```

## Archiving a plan

Use the `plan-archiver` subagent:

> "Archive plan `accounts-group-by-switch`. Implementation landed in
> commit abc1234."

The subagent:
1. reads `docs/plans/<plan_id>.md`,
2. verifies the commit(s) exist and touch the expected files,
3. appends an `## Implementation` section with SHA, author, date,
   short message, and files changed,
4. flips `status: archived` in frontmatter,
5. moves the file to `docs/plans/archive/<plan_id>.md`,
6. updates the index table below.

## Plans index

### Q4 2026 — Open-source launch (execute in this order)

| # | Plan | Status | Depends on |
|---|---|---|---|
| 1 | [q4-licence-and-cla](archive/q4-licence-and-cla.md) | archived | — |
| 2 | [q4-public-repo-readiness](archive/q4-public-repo-readiness.md) | archived | 1 (CONTRIBUTING references CLA) |
| 3 | [q4-supabase-deployment](q4-supabase-deployment.md) | in-progress | Sections 2+4 done; hosting + live demo URL open |
| 4 | [q4-dashboard-design-refresh](archive/q4-dashboard-design-refresh.md) | archived | — |

### Q3 2026 — Stabilisation & debt (execute in this order)

| # | Plan | Status | Depends on |
|---|---|---|---|
| 1 | [q3-test-safety-net](archive/q3-test-safety-net.md) | archived | — |
| 2 | [q3-views-refactor](archive/q3-views-refactor.md) | archived | 1 (e2e green first) |
| 3 | [q3-auth-single-user](archive/q3-auth-single-user.md) | archived | 1 (updates API tests) |
| 4 | [q3-forecast-optional-prophet](archive/q3-forecast-optional-prophet.md) | archived | — (parallel-safe) |
| 5 | [q3-engineering-hygiene](archive/q3-engineering-hygiene.md) | archived | CI after 1; exceptions parallel-safe |
| 6 | [q3-spec-enforcement](archive/q3-spec-enforcement.md) | archived | CI from 5; import-linter ignores burned down by 2 |

See [roadmap → Q3 2026](../roadmap.md#q3-2026-jul-sep-stabilisation--debt)
and [ADR-032](../adr/032-retire-the-controller-layer-views-call-services-directly.md).

### Quick wins (small)

| Plan | Status | Roadmap ref |
|---|---|---|
| [categories-name-unique-per-type](archive/categories-name-unique-per-type.md) | archived | Categories — dogfooding bug |
| [backup-scheduler-active-db-url](archive/backup-scheduler-active-db-url.md) | archived | Settings / data safety — dogfooding bug |
| [import-flow-polish](archive/import-flow-polish.md) | archived | Import — dogfooding UX |
| [transactions-type-labels-i18n](archive/transactions-type-labels-i18n.md) | archived | Transactions — dogfooding bug |
| [transactions-split-discoverability](archive/transactions-split-discoverability.md) | archived | Transactions — dogfooding UX |
| [auth-reset-password-cli](archive/auth-reset-password-cli.md) | archived | Auth (audit P1.10) |
| [dashboard-customize-reset-options](dashboard-customize-reset-options.md) | draft (Q4) | Dashboard |
| [transactions-notes-field](transactions-notes-field.md) | draft (Q4) | Transactions |
| [wizard-action-items-widget](wizard-action-items-widget.md) | draft (Q4) | Wizard |
| [seed-payees-tags-coverage](seed-payees-tags-coverage.md) | draft (Q4) | Seed |
| [seed-payment-calendar](seed-payment-calendar.md) | draft (Q4) | Payment Calendar |
| [settings-panel-color-fix](archive/settings-panel-color-fix.md) | archived | Settings — folded into views-refactor |
| [credit-dark-mode-color-fix](archive/credit-dark-mode-color-fix.md) | archived | Credit — folded into views-refactor |
| [dashboard-chart-fluid-height](archive/dashboard-chart-fluid-height.md) | archived | Dashboard — folded into views-refactor |
| [accounts-group-by-switch](archive/accounts-group-by-switch.md) | archived | Accounts |
| [transactions-colored-amounts](archive/transactions-colored-amounts.md) | archived | Transactions + cross-cutting colours |
| [tags-seed-list](archive/tags-seed-list.md) | archived | Tags |
| [categories-templates](archive/categories-templates.md) | archived | Categories |
| [institutions-logos](archive/institutions-logos.md) | archived | Institutions |
| [wizard-getting-started-mentor](archive/wizard-getting-started-mentor.md) | archived | Wizard → Getting Started |
| [safety-funds-months-bar](archive/safety-funds-months-bar.md) | archived | Wizard → Safety funds |
| [subscriptions-notes](archive/subscriptions-notes.md) | archived | Wizard → Subscriptions |

### Medium

| Plan | Status | Roadmap ref |
|---|---|---|
| [audit-production-readiness](archive/audit-production-readiness.md) | archived | Cross-cutting audit (data-safety / ops lens) |
| [p2-hardening-analysis](archive/p2-hardening-analysis.md) | archived | Auth / API / Settings (audit P2) |
| [sqlite-integrity-scheduled-backups](archive/sqlite-integrity-scheduled-backups.md) | archived | DB / Housekeeping / Settings |
| [migrate-on-startup](archive/migrate-on-startup.md) | archived | Setup / ops (audit P0.4) |
| [currency-nbp-rates](archive/currency-nbp-rates.md) | archived | Settings / FX (audit P1.5) |
| [deploy-local-health](archive/deploy-local-health.md) | archived | Ops / API (audit P1.9) |
| [backup-full-schema-roundtrip](archive/backup-full-schema-roundtrip.md) | archived | Settings / Data |
| [dashboard-edit-mode-drag](archive/dashboard-edit-mode-drag.md) | archived | Dashboard |
| [dashboard-widget-resize](archive/dashboard-widget-resize.md) | archived | Dashboard |
| [import-bank-profiles](import-bank-profiles.md) | in-progress | Import — fixture-backed bank parsers (scaffold done) |
| [import-mapping-wizard](archive/import-mapping-wizard.md) | archived | Import — dogfooding UX |
| [import-history-account-coverage](archive/import-history-account-coverage.md) | archived | Import — dogfooding UX |
| [import-per-file-mapping-memory](archive/import-per-file-mapping-memory.md) | archived | Import — after import-mapping-wizard |
| [wizard-unplanned-radar](wizard-unplanned-radar.md) | draft | Wizard — dogfooding gap (Coming soon tile) |
| [wizard-pay-yourself-salary](wizard-pay-yourself-salary.md) | draft | Wizard — dogfooding gap (Coming soon tile) |
| [reports-money-flow](archive/reports-money-flow.md) | archived | Reports — money flow Sankey |
| [rules-auto-categorisation](archive/rules-auto-categorisation.md) | archived | Import / Rules |
| [payees-identities-automerge](payees-identities-automerge.md) | draft | Payees |
| [settings-week-debug-seed](settings-week-debug-seed.md) | draft | Settings |
| [planned-transactions-post-due](archive/planned-transactions-post-due.md) | archived | Planned transactions |
| [transactions-splits-integrity](archive/transactions-splits-integrity.md) | archived | Transactions |
| [transactions-payee-autocomplete](transactions-payee-autocomplete.md) | draft | Transactions |
| [transactions-upcoming-planned](transactions-upcoming-planned.md) | draft | Transactions |
| [ux-audit-feature-categorization](archive/ux-audit-feature-categorization.md) | archived | UX / IA |
| [ux-sidebar-workflow-and-settings](archive/ux-sidebar-workflow-and-settings.md) | archived | UX — sidebar nav (#42) + settings expansion (#60) |
| [setup-zero-config-bootstrap](archive/setup-zero-config-bootstrap.md) | archived | Setup |
| [net-worth-layout-refresh](archive/net-worth-layout-refresh.md) | archived | Net Worth |
| [transactions-reconcile](archive/transactions-reconcile.md) | archived | Transactions |
| [budgets-realization-view](archive/budgets-realization-view.md) | archived | Budgets |
| [import-multi-file-queue](archive/import-multi-file-queue.md) | archived | Import |
| [forecast-model-presets](archive/forecast-model-presets.md) | archived | Forecast |
| [reports-library](archive/reports-library.md) | archived | Reports |
| [settings-expansion](archive/settings-expansion.md) | archived | Settings |
| [dedupe-suggestions](archive/dedupe-suggestions.md) | archived | Cross-cutting |
| [wizard-safety-funds](archive/wizard-safety-funds.md) | archived | Wizard → Safety funds |
| [wizard-personal-loans](archive/wizard-personal-loans.md) | archived | Wizard → Personal loans |
| [subscriptions-category-driven](archive/subscriptions-category-driven.md) | archived | Wizard → Subscriptions |

### Large

| Plan | Status | Roadmap ref |
|---|---|---|
| [budgets-plan-unification](budgets-plan-unification.md) | draft | Budgets |
| [wizard-what-if-scenarios](wizard-what-if-scenarios.md) | draft | Wizard / Forecast — dogfooding gap (Coming soon tile) |
| [wizard-reminders](wizard-reminders.md) | draft | Wizard → notifications |
| [funds-reservoir-view](funds-reservoir-view.md) | draft | Funds — reservoir view (after reports-money-flow) |
| [dashboard-command-center](archive/dashboard-command-center.md) | archived | Dashboard |
| [budgets-rename-and-payment-calendar](archive/budgets-rename-and-payment-calendar.md) | archived | Budgets + new Payment Calendar |
| [credit-first-class](archive/credit-first-class.md) | archived | Credit |
| [wizard-monthly-readiness](archive/wizard-monthly-readiness.md) | archived | Wizard → Monthly Readiness |
| [wizard-subscriptions](archive/wizard-subscriptions.md) | archived | Wizard → Subscriptions |
| [wizard-budget-builder](archive/wizard-budget-builder.md) | archived | Wizard → Budget Builder |
| [wizard-cross-panel-data](archive/wizard-cross-panel-data.md) | archived | Wizard → cross-panel data flow |
