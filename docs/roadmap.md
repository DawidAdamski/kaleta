# Roadmap

Updated 2026-07-03. Replaces the 2026-04-20 backlog, which has been
almost fully delivered (see [`plans/archive/`](plans/archive/) — 27
shipped plans). Format: current quarter in detail, next quarter
sketched, longer-term as directions.

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

## Q3 2026 (Jul–Sep): Stabilisation & debt

Theme: **make the codebase honest, tested, and secure enough to open.**
New features are on hold except where they fall out of refactoring.

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

## Q4 2026 (Oct–Dec): Open-source launch — sketch

- **Licence decision** (ADR): permissive core + enterprise modules
  (Baserow-style) vs. sustainable-use licence (n8n-style). Decide
  before the repo is public; relicensing later is painful.
- Public-repo readiness: CONTRIBUTING, SECURITY.md, issue templates,
  code of conduct, publish the mkdocs site, hosted demo instance with
  seed data.
- First-run experience for strangers: zero-config bootstrap
  (`setup-zero-config-bootstrap` draft), English-first i18n audit,
  category/tag templates on first run.
- Resume feature work from the draft backlog, interleaved ~50/50 with
  remaining debt.
- Groundwork for the paid tier: feature-flag mechanism separating
  core from commercial modules (flags only — no AI features yet).

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
