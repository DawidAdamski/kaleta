# Roadmap

Updated 2026-07-05. Replaces the 2026-04-20 backlog. Format: current
quarter in detail, next quarter sketched, longer-term as directions.

**Status: Q3 delivered in full (2026-07-05), ahead of schedule.** All
five workstreams shipped — see the Q3 section below and
[`plans/archive/`](plans/archive/). Q4 is now the active quarter.

## Strategic direction: open-core

Kaleta aims to be an open-source self-hosted personal finance app with
a commercial offering on top — the Baserow / n8n model:

- **Core is free and fully usable.** Budgeting, transactions, import,
  forecasting, credit tracking — no artificial limits.
- **Paid tier = AI + hosting.** LLM-driven features (auto
  categorisation, anomaly explanations, narrative monthly summaries)
  and a managed hosted instance are the commercial layer.
- **Consequence for priorities:** before the repo can go public and a
  paid tier can exist, the app needs authentication, a test safety
  net, a slim install, and code that outside contributors can navigate.
  That is what Q3 is for.

Standing principles carried over from the previous roadmap:

- Consistent semantic colors (income green, expense red, transfer
  neutral) everywhere.
- YNAB-style "every złoty is assigned" budgeting philosophy.
- Auto-detect similarity, propose merge (payees, categories, tags).

---

## Q3 2026 (Jul–Sep): Stabilisation & debt {#q3-2026-jul-sep-stabilisation--debt}

Theme: **make the codebase honest, tested, and secure enough to open.**

> **DELIVERED 2026-07-05.** All five workstreams complete:
> views refactor (8 packages split, zero direct data access in views,
> import-linter contract with no exceptions), test safety net
> (84 API integration tests, 50 e2e on an ephemeral isolated
> instance), single-user auth (sessions, route guard, API bearer
> tokens, secure defaults), Prophet as optional extra (`kaleta:slim`
> 524 MB vs `kaleta:full` 973 MB, seasonal-naive fallback), and
> hygiene + spec enforcement (exception hierarchy, logging, CI,
> BDD↔test coverage gate, doc link-checker, 32 ADRs split out).
> Plans archived in [`plans/archive/`](plans/archive/). The section
> below is kept as the historical spec.

### 1. Views refactor — kill the god-objects

*Problem:* `views/reports_canned.py` (1 247 LOC) and
`views/transactions.py` (1 234 LOC) concentrate rendering, state, and
business logic. `import_view.py`, `settings.py`, and
`dashboard_widgets.py` are close behind. The `controllers/` package
declared in the architecture is empty.

- Extract shared UI components: transaction table, amount colouring
  helper, filter bar, empty states. One component, used everywhere.
- Split each 800+ LOC view into a thin page module + per-section
  components, target ≤400 LOC per file.
- **ADR required:** either implement the controller layer as
  documented, or remove it from `CLAUDE.md`/`architecture.md` and
  document the actual pattern (views → services). No silent drift.
- Exit criteria: no view file over 500 LOC; architecture docs match
  reality.

### 2. Test safety net

*Problem:* services have solid unit coverage, but 15.7k LOC of views
and the API have none. `docs/bdd.md` scenarios exist but aren't
executed.

- API integration tests for all `api/v1/` routes (ASGI test client,
  in-memory SQLite).
- Playwright e2e for the 5 highest-risk flows from `bdd.md`:
  add/edit/split transaction, CSV import, budget vs actual, setup
  wizard, transfer detection.
- Run both suites in CI on every PR (see workstream 5).
- Exit criteria: refactor from workstream 1 lands with green e2e —
  the suites exist to make that refactor safe, so build them first.

### 3. Authentication

*Problem:* no auth at all; default config binds `0.0.0.0`. Blocks
public release, LAN deployment, and any paid tier.

- Single-user password auth: login page, server-side sessions,
  password set on first run / via env var.
- API bearer tokens for the REST API (create/revoke in Settings).
- Enforce non-default `KALETA_SECRET_KEY` outside debug mode; default
  bind to `127.0.0.1` in web mode.
- Design the user model so multi-user/workspaces (2027) is a
  migration, not a rewrite — `user_id` FK on user-owned tables from
  day one, even while there is exactly one user.

### 4. Slim the install

*Problem:* Prophet pulls ~300 MB (cmdstan) for one feature; hard
import with no fallback.

- Move Prophet to an optional extra: `uv sync --extra forecast`.
- Fallback forecaster (seasonal-naive or rolling-average with simple
  confidence band) when Prophet is absent; Forecast view degrades
  gracefully with a hint.
- Two Docker images: `kaleta:slim` and `kaleta:full`.

### 5. Engineering hygiene

- Custom exception hierarchy (`KaletaError` → domain errors);
  services stop raising bare `ValueError`; views map exceptions to
  user-facing toasts consistently.
- Structured logging (module loggers, request logging in API mode);
  extend the existing audit log to cover auth events.
- CI pipeline (GitHub Actions): ruff, mypy, pytest, e2e smoke on PR.
- Triage the 18 draft plans in [`plans/`](plans/): fold the
  cosmetic ones into workstream 1's refactor, keep genuinely new
  features (`payees-identities-automerge`,
  `setup-zero-config-bootstrap`, `wizard-reminders`, …) for Q4.

---

## Q4 2026: Open-source launch {#q4-2026-open-source-launch}

Active quarter (started early — Q3 delivered 2026-07-05). Theme:
**a stranger can find, install, trust, and contribute to Kaleta.**
Order matters: the licence gates everything public.

### 1. Licence decision (first, blocking)

ADR + `LICENSE` file: AGPL-3.0 core + CLA + proprietary licence for
commercial modules (recommended) vs. sustainable-use (n8n-style).
Consult a lawyer before the repo goes public; relicensing later is
painful. CLA tooling (e.g. CLA-assistant) ready before the first
external PR.

### 2. Public-repo readiness

- CONTRIBUTING.md (workflow: plans, Working Agreement, verify.sh),
  SECURITY.md, issue/PR templates, code of conduct.
- History audit before flipping to public: secrets scan on full git
  history, `kaleta.db`/backup files out of the repo and .gitignored.
- Publish the mkdocs site; hosted demo instance with seed data.
- Housekeeping carried over from Q3: consolidate the duplicated dev
  dependency definitions (optional-dependencies `dev` vs
  dependency-group `dev`) into one; verify.sh fails fast with a hint
  when dev tools are missing.

### 3. First-run experience for strangers

- Zero-config bootstrap (`setup-zero-config-bootstrap` draft).
- English-first i18n audit; category/tag templates offered on first
  run.

### 4. Feature work resumes

Deferred drafts (tagged `deferred_to: q4-2026`), interleaved ~50/50
with remaining polish: payees identities automerge, transactions QoL
(notes, payee autocomplete, upcoming planned), import per-file
mapping memory, dashboard polish, wizard reminders and action-items
widget, budgets plan unification, UX audit.

### 5. Paid-tier groundwork

Feature-flag mechanism separating core from commercial modules
(flags only — no AI features this quarter).

## 2027 directions

- Multi-user & workspaces (household sharing) on the Q3 user-model
  groundwork.
- Commercial tier v1: AI categorisation + monthly narrative summary
  behind the paywall; managed hosting.
- Bank connectivity (open banking / PSD2 aggregator) replacing manual
  CSV import as the primary path.
- Mobile: PWA push notifications (bill reminders from Payment
  Calendar), offline entry.

---

## Backlog (unscheduled)

Small items from the draft plans not scheduled above — pick up
opportunistically: dashboard polish
(`dashboard-customize-reset-options`, `dashboard-chart-fluid-height`),
transactions QoL (`transactions-notes-field`,
`transactions-payee-autocomplete`, `transactions-upcoming-planned`),
import mapping memory (`import-per-file-mapping-memory`), seed data
coverage (`seed-*`), colour fixes (`*-color-fix`), UX audit
(`ux-audit-feature-categorization`), wizard extras
(`wizard-action-items-widget`, `wizard-reminders`,
`budgets-plan-unification`).

### Plan `roadmap_ref` anchors {#plan-roadmap-ref-anchors}

Stable heading IDs for cross-links from [`plans/`](plans/). Each entry
maps draft or shipped work to a roadmap area.

| Anchor | Area |
|---|---|
| [Dashboard](#dashboard) | Dashboard widgets and layout |
| [Transactions](#transactions) | Ledger, payees, planned items |
| [Import](#import) | CSV import and mapping |
| [Settings](#settings) | Preferences, data, audit |
| [Setup](#setup) | First-run bootstrap |
| [Seed](#seed) | Demo / dev seed data |
| [Payment Calendar](#payment-calendar) | Recurring payment schedule |
| [Accounts](#accounts) | Account CRUD and grouping |
| [Budgets](#budgets) | Budget views and planning |
| [Budgets (current view)](#budgets-current-budgets-view) | Realization + plan tabs |
| [Categories](#categories) | Category tree |
| [Credit](#credit) | Cards, loans, calculator |
| [Forecast](#forecast) | Balance projection |
| [Institutions](#institutions) | Bank / broker grouping |
| [Net Worth](#net-worth) | Assets and liabilities summary |
| [Reports](#reports) | Canned and custom reports |
| [Tags](#tags) | Transaction tags |
| [UX](#ux) | Information architecture audits |
| [Cross-cutting principles](#cross-cutting-principles) | Colours, dedupe philosophy |
| [Auto dedupe suggestions](#cross-cutting-automatic-deduplication-suggestions) | Payee/category merge proposals |

#### Dashboard {#dashboard}
Dashboard polish and widget work (see backlog paragraph above).

#### Transactions {#transactions}
Transaction QoL: notes, payee autocomplete, upcoming planned overlay.

#### Import {#import}
CSV import mapping memory and multi-file queue.

#### Settings {#settings}
Settings tabs, week start, debug seed, panel styling.

#### Setup {#setup}
Zero-config bootstrap for first-time strangers.

#### Seed {#seed}
Seed script coverage for payees, tags, payment calendar.

#### Payment Calendar {#payment-calendar}
Planned/recurring payment schedule in the wizard.

#### Accounts {#accounts}
Account views, grouping, institution assignment.

#### Budgets {#budgets}
Budget realization, annual plan, unification.

#### Budgets (current view) {#budgets-current-budgets-view}
The `/budgets` Realization + Plan tab experience.

#### Categories {#categories}
Category templates and tree management.

#### Credit {#credit}
Credit cards, loans, calculator, dark-mode styling.

#### Forecast {#forecast}
Prophet / fallback balance forecasting.

#### Institutions {#institutions}
Institution CRUD and logos.

#### Net Worth {#net-worth}
Net worth layout and physical assets.

#### Reports {#reports}
Canned reports library.

#### Tags {#tags}
Tag seed list and transaction tagging.

#### UX {#ux}
Feature categorization and IA audits.

#### Cross-cutting principles {#cross-cutting-principles}
Semantic colours, YNAB-style budgeting, dedupe philosophy.

#### Auto dedupe suggestions {#cross-cutting-automatic-deduplication-suggestions}
Automatic payee and identity merge proposals.
