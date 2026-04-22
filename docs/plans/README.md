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

### Quick wins (small)

| Plan | Status | Roadmap ref |
|---|---|---|
| [accounts-group-by-switch](archive/accounts-group-by-switch.md) | archived | Accounts |
| [transactions-colored-amounts](archive/transactions-colored-amounts.md) | archived | Transactions + cross-cutting colours |
| [tags-seed-list](archive/tags-seed-list.md) | archived | Tags |
| [categories-templates](archive/categories-templates.md) | archived | Categories |
| [institutions-logos](archive/institutions-logos.md) | archived | Institutions |
| [wizard-getting-started-mentor](archive/wizard-getting-started-mentor.md) | archived | Wizard → Getting Started |

### Medium

| Plan | Status | Roadmap ref |
|---|---|---|
| [net-worth-layout-refresh](archive/net-worth-layout-refresh.md) | archived | Net Worth |
| [transactions-reconcile](archive/transactions-reconcile.md) | archived | Transactions |
| [budgets-realization-view](budgets-realization-view.md) | draft | Budgets |
| [import-multi-file-queue](import-multi-file-queue.md) | draft | Import |
| [forecast-model-presets](archive/forecast-model-presets.md) | archived | Forecast |
| [reports-library](archive/reports-library.md) | archived | Reports |
| [settings-expansion](settings-expansion.md) | draft | Settings |
| [dedupe-suggestions](dedupe-suggestions.md) | draft | Cross-cutting |
| [wizard-safety-funds](wizard-safety-funds.md) | draft | Wizard → Safety funds |
| [wizard-personal-loans](wizard-personal-loans.md) | draft | Wizard → Personal loans |

### Large

| Plan | Status | Roadmap ref |
|---|---|---|
| [dashboard-command-center](archive/dashboard-command-center.md) | archived | Dashboard |
| [budgets-rename-and-payment-calendar](budgets-rename-and-payment-calendar.md) | draft | Budgets + new Payment Calendar |
| [credit-first-class](credit-first-class.md) | draft | Credit |
| [wizard-monthly-readiness](wizard-monthly-readiness.md) | draft | Wizard → Monthly Readiness |
| [wizard-subscriptions](wizard-subscriptions.md) | draft | Wizard → Subscriptions |
| [wizard-budget-builder](wizard-budget-builder.md) | draft | Wizard → Budget Builder |
