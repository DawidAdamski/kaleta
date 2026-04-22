# Roadmap & Backlog

Captured from product brainstorming on 2026-04-20. Organised by module.
Each entry states the **intent** (what the user wants), a **proposed
approach** (one sketch, not the final design), and **open questions**.
This is a planning document — nothing here is implemented yet.

Deep-dives for the two concepts that outgrew bullet form:

- [Dashboard as Command Center](product/dashboard.md)
- [Financial Wizard (Assistant Model)](product/financial-wizard.md)

## Cross-cutting principles

- **Consistent semantic colors.** Income is always green, expense red,
  transfer neutral. Applies to transactions, planned transactions,
  budgets, reports, dashboard widgets — everywhere. Pick one token and
  use it globally. Same rule for icons.
- **YNAB-style "every złoty is assigned."** Budgeting should lean on
  this philosophy rather than pure report-of-actuals. Monthly Readiness
  checks surface any zloty that is unassigned.
- **AI features behind paywall.** Any LLM-driven analysis (auto
  categorisation, anomaly explanations, narrative monthly summary) is
  reserved for a paid tier. Core app must stay fully usable without AI.
- **Auto-detect similarity, propose merge.** Payees, categories, tags —
  when the user is about to add a duplicate, Kaleta suggests merge
  rather than silently accepting it.

## Per-module backlog

### Dashboard

- **Command-centre philosophy** — see
  [deep-dive](product/dashboard.md). Widgets, collapse, TLDR layout.

### Accounts

- **Group-by as switch, not dropdown.**
  - *Intent:* faster toggling between Type / Institution grouping.
  - *Approach:* replace `ui.select` with `ui.toggle` (2-value); clicking
    either option snaps to it without closing a menu.
  - *Open:* if a third grouping ever appears (e.g. Currency), does the
    toggle scale, or do we add a chip group?

### Net Worth

- **Visual symmetry between Assets and Liabilities tables.**
  - *Intent:* the two sides feel balanced; columns align; empty states
    match.
  - *Approach:* audit widths/paddings; lock the two cards to identical
    min-heights; share the same table component.
- **Physical items come first, aggregated items after.**
  - *Intent:* physical holdings (real estate, vehicles, jewellery,
    collectibles) are the net-worth-native concept; account balances
    are "borrowed" from other views.
  - *Approach:* reorder sections — Physical assets → Accounts-derived
    assets → Liabilities (mirrored: Physical → Accounts-derived).
  - *Open:* does this apply to Liabilities too (physical debts like
    promissory notes vs bank loans aggregated from accounts)?

### Reports

- **Reports reusable as dashboard widgets.**
  - *Intent:* once a report is built, embed it on the dashboard.
  - *Approach:* every report renders a `Widget` component; Report
    Builder gets a "Pin to dashboard" action; widget receives the
    serialised report spec as its config.
- **Pre-built report library.**
  - *Intent:* new users get value immediately without needing to learn
    the builder.
  - *Approach:* ship a curated set. Candidates:
    - Monthly spend by category (top 10)
    - Income vs expenses, last 12 months
    - Cashflow run-rate (rolling 3-month average)
    - Recurring/subscription drain per month
    - Largest transactions of the month
    - Category trend (YoY, selected category)
    - Spending by payee (top 20)
    - Budget vs actual — monthly
    - Net-worth delta — monthly
  - *Open:* which five do we ship first? which are best suited to
    dashboard widgets (small tile) vs full-page reports?

### Transactions

- **Colored amount column.**
  - *Intent:* expense = red, income = green, transfer = neutral; same
    styling as Planned Transactions uses today, unified across the app.
  - *Approach:* reuse the planned-tx renderer. Add a single helper that
    returns the colour class for `kind + amount sign`.
- **Reconcile feature.**
  - *Intent:* mark a transaction as confirmed against the bank
    statement; surface un-reconciled transactions for review.
  - *Approach:* boolean `reconciled_at` timestamp on `Transaction` +
    bulk reconcile action on the table. Optional "Reconcile up to date
    X" action that tags everything up to a cutoff.
  - *Open:* does reconcile live per-account (one date per account), or
    per-transaction only?

### Budgets (current "Budgets" view)

- **Viewed as realization report, not editor.**
  - *Intent:* this page is where the user *checks* how the month is
    going. Editing happens in Budget Plan.
  - *Approach:* remove the edit affordance from this page; it becomes
    read-only. Edit always routes to Budget Plan.
- **Small donut / progress visualisations per category.**
  - *Intent:* a glance tells the user where they stand; no table
    reading required.
  - *Approach:* per-category donut — spent vs planned; red halo when
    over, amber when near, green when under.
- **Proposed rename.** See *Budget Plan rename* below.

### Budget Plan → Budgets rename & new Payment Calendar

- **Rename `Budget Plan` → `Budgets` (planning + realization).**
  - *Intent:* the plan page is the canonical budget editor; merging
    the realisation view into it makes one destination instead of two.
- **Old `Budgets` slot becomes a new `Payment Calendar` view.**
  - *Intent:* a month-at-a-glance calendar of planned cash outflows
    and inflows (recurring bills, salary, transfers), separate from
    the transactional register.
  - *Approach:* calendar grid (month / week), cells show planned
    transactions due that day, totals per week.
  - *Open:* does it become the new home for managing recurring
    transactions, or does Planned Transactions stay as the list view
    and Payment Calendar is purely visualisation?

### Import

- **"+" button must work and be discoverable.**
  - *Intent:* fix the current UX where it isn't obvious where to click.
  - *Approach:* make the uploader the primary hero element; single,
    unambiguous "Add statement" CTA.
- **Multi-file import per account.**
  - *Intent:* user may have many CSVs to import for the same account,
    or a batch across several accounts in one session.
  - *Approach:* queue uploader — drop many files, resolve account +
    mapping per file, process in batch with an undo window.
  - *Open:* behaviour on duplicate detection across files; progress
    display for long queues.

### Forecast

- **Expose multiple Prophet configurations.**
  - *Intent:* power users want to compare model variants
    (seasonality on/off, changepoint range, trend flexibility).
  - *Approach:* `ui.select` of named model presets ("Conservative",
    "Seasonal-aware", "High-flex"); later an "Advanced" tab for raw
    parameters. Compute on demand, cache by (account, preset).

### Credit / Loans

- **Track credits inside the app.**
  - *Intent:* a credit product (mortgage, personal loan) lives as a
    first-class entity, not just repayment transactions.
  - *Approach:* `Credit` model — principal, rate, start date, schedule,
    linked account. Monthly instalments auto-generated as planned
    transactions. Payment transactions link back to the credit so the
    remaining balance is always current.
  - *Open:* the existing Credit Calculator view should co-exist — one
    for simulating, the other for tracking a real commitment. Keep
    both? merge?
- **Register of personal loans (lent / borrowed).**
  - *Intent:* track money lent to or borrowed from individual people,
    separately from bank credit.
  - *Approach:* `PersonalLoan` entity with counterparty (free text or
    payee reference), direction (lent / borrowed), amount, expected
    return date, status. Optional linked transaction when settled.
  - Implemented as part of the Wizard module — see wizard deep-dive.

### Institutions

- **Bank logos.**
  - *Intent:* instantly recognise an institution by its logo.
  - *Approach:* `Institution.logo_path` (optional). Folder of
    Polish bank logos (PKO, mBank, Santander, ING, Pekao, BNP
    Paribas, Millennium, Alior, Credit Agricole, …) shipped or
    user-uploaded. Fallback: first-letter avatar.

### Categories

- **Shippable templates.**
  - *Intent:* a new user doesn't have to invent a category tree from
    scratch.
  - *Approach:* a few named templates (e.g. "Polish household",
    "Single person", "Freelancer", "Student") loadable from Settings
    or on first run. Each template is a JSON in the repo.

### Tags

- **Seed tags.**
  - *Intent:* common tags exist out-of-the-box: "paid by card",
    "transfer", "cash", "online", "subscription", "refundable",
    "business".
  - *Approach:* seed migration or first-run insertion. User can
    delete freely.

### Settings

- **Expand considerably.** Current page is thin. Future sections:
  - Appearance (theme, colour accent)
  - Locale (language, currency, date format)
  - Notifications (email, push, messenger webhook)
  - Data (export, backup, reset)
  - AI features (API key, model, privacy toggles)
  - Paywall / subscription to Kaleta itself (future)
  - Import defaults (encoding, CSV column mapping memory)

### Cross-cutting: automatic deduplication suggestions

- **Intent:** catch near-duplicates before they clutter the data.
- **Approach:** background job scans payees, categories, tags;
  proposes merges ranked by similarity (case-insensitive Levenshtein,
  possibly phonetic). Surfaces in a settings screen and/or as an
  inline prompt during entry.
- Ties into the existing merge flow in Payees.

## Priorities (draft — to confirm)

- **Quick wins (low effort, high user value):**
  - Accounts group-by as switch
  - Transactions amount colouring (consistent tokens)
  - Tags seed list
  - Institution logos (needs asset folder first)
- **Medium (clear scope, moderate effort):**
  - Net Worth reordering + symmetry pass
  - Pre-built reports (pick 5)
  - Budget view → realization-only (remove edit)
  - Multi-file import queue
  - Reconcile on transactions
- **Large (multi-PR, design required):**
  - Dashboard as Command Center
  - Budget Plan ↔ Budgets rename + Payment Calendar
  - Financial Wizard sections (Monthly Readiness, Subscriptions,
    Safety Funds, Budget Builder, Personal Loans)
  - Credit as first-class entity
  - Forecast model presets

Priorities are a proposal; reorder freely.
