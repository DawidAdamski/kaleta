---
plan_id: audit-production-readiness
title: Audit — production readiness for daily local use with real data (2026-07-25)
area: cross-cutting
effort: medium
status: archived
archived_at: 2026-08-26
roadmap_ref: ../../roadmap.md#cross-cutting-principles
---

# Audit — production readiness for daily local use

**Question:** what is missing before running Kaleta locally, every day, on
real financial data — and trusting it not to lose that data?

**Method:** static analysis of the full source tree (branch
`docs/plan-drafts`, HEAD `d05b0be`). No tests were run and the app was not
exercised live; findings are code-level facts unless marked *(unverified)*.
This audit complements `audit-planned-vs-code.md` (feature-vs-spec lens)
with a **data-safety / operations lens** that no existing plan covers.

**Verdict:** the app is functionally ready for daily use — the feature set
(import, budgets, 10+ canned reports, forecast, net worth, subscriptions,
payment calendar) comfortably covers a daily-driver workflow. What is *not*
ready is the **data-safety layer**: backup coverage, SQLite integrity
pragmas, and migration-on-upgrade. Those three are the P0s. Until they land,
the only trustworthy backup is a file copy of the `.db` itself.

---

## P0 — data safety (fix before real data goes in)

### 1. Backup covers 8 of ~25 tables — restore silently loses data

`services/backup_service.py` `_TABLES` lists only: institutions, categories,
accounts, assets, budgets, currency_rates, transactions,
transaction_splits.

**Not exported and not restored:** payees, tags, `transaction_tags` links,
planned_transactions, subscriptions, personal_loans (+repayments,
counterparties), credit_card_profiles, loan_profiles, reserve_funds,
monthly_readiness, yearly_plans, saved_reports, users, api_tokens,
dismissed_candidates, audit_log.

A user who relies on Settings → Data → Export and later restores gets back
a ledger with **no payees (FK dangling on `transactions.payee_id`), no
tags, no subscriptions, no loans, no plans, and no login user**. Two
compounding defects:

- `metadata.json` records only `version: "1"` — **no alembic revision
  stamp**, so a backup restored into a different schema version is not
  detected; unknown columns are silently dropped (`cols = [c for c in
  rows[0] if c in allowed]`).
- Restore `DELETE`s only the 8 listed tables, so restoring into a non-empty
  DB produces a hybrid state (old payees + restored transactions).

**Fix:** derive the table list from `Base.metadata.sorted_tables` (single
source of truth — new models join automatically), stamp the current alembic
revision into `metadata.json`, refuse restore on revision mismatch (offer
"migrate backup" path later), and fail loudly on unknown columns instead of
dropping them.

- `uv run pytest tests/unit/services/test_backup_service.py -q` — round-trip
  test: seed every model, export, wipe, restore, assert row counts equal.

### 2. No automated backups

Backup exists only as a manual button in Settings → Data. A daily-driver
finance app needs scheduled, retained, tested backups.

**Fix (app side):** a backup-on-schedule option — simplest robust version:
on app start and then every N hours, `VACUUM INTO` (SQLite) a timestamped
copy to a configurable directory, keep last K. `VACUUM INTO` backs up
**everything** (all 25 tables), so it also mitigates finding 1 immediately.
**Workaround (today, ops side):** cron/launchd job:
`sqlite3 ~/.kaleta/kaleta.db "VACUUM INTO 'backups/kaleta-$(date +%F).db'"`
into a cloud-synced folder.

### 3. SQLite runs without integrity pragmas

No `event.listens_for(engine, "connect")` handler anywhere. Consequences:

- `PRAGMA foreign_keys` is **OFF by default in SQLite** → FK constraints in
  the schema are not enforced at runtime. ORM-level cascades cover normal
  paths, but any raw SQL, partial restore, or future bug can create orphans
  invisibly. (backup/data services even toggle `foreign_keys OFF/ON`,
  assuming it was ON — it never was.)
- No `journal_mode=WAL` → reader/writer blocking; with UI + API + (future)
  scheduled jobs on the same file, intermittent `database is locked` errors.
- No `busy_timeout` → those errors surface immediately instead of retrying.

**Fix:** one connect-listener in `db/session.py` setting
`foreign_keys=ON`, `journal_mode=WAL`, `busy_timeout=5000`,
`synchronous=NORMAL`. Small change, large integrity payoff. Add an orphan
check (`PRAGMA foreign_key_check`) to housekeeping.

### 4. Migrations don't run on upgrade — schema drift after `git pull`

`setup_service.activate_database()` runs `alembic upgrade head` **only when
a database is first activated** via the setup wizard. `main._preload_config()`
reconfigures the engine from `~/.kaleta/config.json` but never migrates.
After pulling a new version with new migrations, the app starts against an
outdated schema → runtime errors at first query touching a new column.

Related doc gotcha: README's quick start (`uv run alembic upgrade head`)
migrates `sqlite:///kaleta.db` **in the CWD** (from `settings.db_url`),
while the app actually uses the DB from `~/.kaleta/config.json` — alembic
CLI and the app can silently target **different databases**. Correct manual
invocation today is `KALETA_MIGRATE_URL=<real-url> uv run alembic upgrade head`.

**Fix:** in `_preload_config()`, compare the DB's alembic revision to head;
auto-upgrade (with a pre-migration `VACUUM INTO` safety copy — ties into
finding 2) or refuse to start with a clear message. Update README.

→ **Plan:** [`migrate-on-startup.md`](migrate-on-startup.md) (archived).

---

## P1 — daily-run friction (fix in the first weeks of dogfooding)

### 5. Currency rates are manual-only — no NBP integration

`currency_rate_service` stores rates from manual entry or derived from
transfers; there is **no network fetch anywhere in `src/`**. With foreign-
currency accounts (e.g. Revolut EUR/USD), net worth and reports drift
between manual updates.

**Fix:** optional NBP table-A fetcher (public JSON API, no key), triggered
on app start / on demand from Settings, storing into the existing
`currency_rates` table. Keep it optional-and-offline-safe (core principle:
app works with no network).

→ Plan: [`currency-nbp-rates`](currency-nbp-rates.md)

### 6. Planned transactions are never posted

Payment Calendar computes occurrences and an overdue bucket, but nothing
converts a due planned transaction into a real one — no scheduler, no
"post now" action found in the planned-transactions service/views
*(UI-level action unverified)*. Daily-run consequence: recurring bills must
be re-entered manually or re-imported, and the ledger lags the calendar.

**Fix:** an explicit "post due occurrences" action (button on Payment
Calendar / dashboard widget listing due items with one-click post), then an
opt-in auto-post on app start. Full background scheduling is unnecessary
for a locally-run app — on-start + on-demand covers it.

→ Plan: [`planned-transactions-post-due`](planned-transactions-post-due.md)

### 7. Import profiles: generic CSV + mBank only

`import_service` auto-detects mBank and falls back to a generic
header-alias parser. Any other bank in daily use (seed data suggests PKO,
Revolut) depends on the generic parser coping with that bank's export
format — column aliases, date formats, encoding. Per-file mapping memory is
already a draft plan (`import-per-file-mapping-memory`).

**Fix:** during the first month of dogfooding, collect one real export per
bank actually used; add a profile (or alias entries + a fixture test) per
format that the generic parser mishandles. Driven by real files, not
speculation.

→ Plan: [`import-bank-profiles`](../import-bank-profiles.md)

### 8. No rule-based auto-categorisation

Confirmed greenfield (KAL-RUL in `audit-planned-vs-code.md`). For a daily
import workflow this is the single biggest time cost: every import session
is manual categorisation. The AI tier is the roadmap answer, but a simple
core-tier rule engine (payee/description contains X → category Y, rules
learned from past corrections) would cut daily effort dramatically and is
the natural precursor to the paid AI feature.

→ Plan: [`rules-auto-categorisation`](rules-auto-categorisation.md)

### 9. Local deployment story: no autostart, no health endpoint

- No launchd (macOS) / systemd unit example in docs — daily run currently
  means a terminal window. **Fix:** ship `docs/deploy-local.md` with a
  launchd plist (`KALETA_MODE=web`, `KALETA_HOST=127.0.0.1`, WorkingDirectory
  pinned) + systemd unit.
- No `/health` or `/api/v1/health` endpoint (grep confirms) — nothing for a
  monitor/uptime check to probe. **Fix:** trivial unauthenticated health
  route returning app version + DB reachability + pending-migration flag
  (dovetails with finding 4).
- NiceGUI session storage (`.nicegui/`) lands in the **CWD** — the repo
  root currently holds ~200 accumulated session files, and no GC. Pinning
  WorkingDirectory (launchd) plus a startup sweep of stale storage files
  fixes both.

→ Plan: [`deploy-local-health`](deploy-local-health.md)

### 10. Password reset requires hand-editing the database

Single user + argon2 + no CLI reset path: a forgotten password means
manually deleting the user row in sqlite so the create-account bootstrap
reappears *(flow inferred from `auth_state()`; unverified end-to-end)*.
**Fix:** `uv run kaleta --reset-password` (or documented sqlite one-liner
in SECURITY.md / getting-started).

→ Plan: [`auth-reset-password-cli`](auth-reset-password-cli.md)

---

## P2 — hardening & analysis ergonomics (nice-to-have for LAN/long-term)

→ **Plan:** [`p2-hardening-analysis.md`](p2-hardening-analysis.md) (archived).

11. **No login rate-limiting, no session expiry.** → addressed in plan WP2
    (`LoginRateLimiter` 5/15m + `KALETA_SESSION_TTL_HOURS` default 72).
12. **API accepts the UI session cookie without CSRF protection.** → WP2:
    cookie auth is read-only (safe methods only); mutations require Bearer.
13. **`KALETA_API_TOKEN` bootstrap.** *Correction:* already accepted via
    `ApiTokenService._authenticate_env_token` when a real user exists.
    Remaining gap (fresh DB / no user) closed in WP1 by creating a locked
    `api` bootstrap user on `KALETA_MODE=api` startup when the env token is set.
14. **API coverage limits external analysis.** → WP4 read-only routes:
    subscriptions, personal-loans, reserve-funds, net-worth, reports/cashflow,
    reports/income-statement.
15. **No one-click full ledger export.** → WP3 Settings → Data ledger CSV.
16. **Repo-root data files.** NiceGUI storage already under `~/.kaleta/nicegui`
    (deploy-local-health). WP1 defaults `KALETA_DB_URL` / setup wizard to
    `~/.kaleta/kaleta.db` and warns on leftover `.nicegui`/`*.db` in a git CWD.
    History scrub remains with q4-public-repo-readiness.

---

## Will it support daily analysis? (assessment, no action needed)

Yes — this is already the strongest part of the app:

- **Reports:** 10 canned (income statement, cash flow, savings rate,
  budget variance, YoY, top merchants, largest transactions, spending by
  category, net worth statement, YTD) + custom report builder with saved
  reports, all with CSV export.
- **Dashboard:** ~20 widgets (cashflow, net-worth trend, savings-rate KPI &
  trend, budget variance, predicted-30d, top merchants…), customisable
  layout.
- **Forecast:** Prophet optional with honest naive fallback.
- **Recurring-cost visibility:** subscriptions detector (+dismissed
  candidates), payment calendar with overdue bucket, monthly readiness.
- **Data hygiene tooling:** dedupe service (payees/categories merge),
  housekeeping view, audit log with trimming.

The gaps that will actually be felt in daily analysis are the P1 items
(stale FX rates, manual categorisation, unposted planned transactions) —
not missing reports.

## Suggested implementation order

Implementation proceeds as **one plan = one branch = one PR**
(Multitask-friendly: pick up one plan file per agent).

| # | Item | Effort | Payoff | Plan |
|---|------|--------|--------|------|
| 1 | SQLite pragmas listener (P0.3) | S | integrity + concurrency, one file | [`sqlite-integrity-scheduled-backups`](sqlite-integrity-scheduled-backups.md) |
| 2 | Auto-migrate on start + README fix (P0.4) | S | safe upgrades | (fold into integrity / setup plans) |
| 3 | Backup from `Base.metadata` + revision stamp (P0.1) | M | trustworthy restore | [`backup-full-schema-roundtrip`](backup-full-schema-roundtrip.md) |
| 4 | Scheduled `VACUUM INTO` backups + retention (P0.2) | S–M | set-and-forget safety | [`sqlite-integrity-scheduled-backups`](sqlite-integrity-scheduled-backups.md) |
| 5 | launchd/systemd doc + `/health` + storage path (P1.9) | S | true daily-run setup | [`deploy-local-health`](deploy-local-health.md) |
| 5b | CLI password reset (P1.10) | S | recovery without DB surgery | [`auth-reset-password-cli`](auth-reset-password-cli.md) |
| 6 | NBP rate fetch (P1.5) | S–M | correct multi-currency numbers | [`currency-nbp-rates`](currency-nbp-rates.md) |
| 7 | "Post due" for planned transactions (P1.6) | M | calendar ↔ ledger closes | [`planned-transactions-post-due`](planned-transactions-post-due.md) |
| 8 | Import profiles from real bank files (P1.7) | M | painless weekly import | [`import-bank-profiles`](../import-bank-profiles.md) |
| 9 | Rule-based auto-categorisation (P1.8) | M–L | biggest daily time-saver | [`rules-auto-categorisation`](rules-auto-categorisation.md) |

Items 1–5 are the "safe to move real data in" gate; 5b and 6–9 are
the "enjoyable daily driver" gate (5b can ship anytime). P2 items
slot in opportunistically via the Chore inbox.

## Interim runbook (before items 1–5 land)

1. Keep the production DB **outside the repo**, e.g.
   `~/KaletaData/kaleta.db` (choose via setup wizard).
2. `.env` in a pinned working directory: `KALETA_SECRET_KEY=<random>`,
   `KALETA_HOST=127.0.0.1`.
3. **Backup = copy of the `.db` file** (cron:
   `sqlite3 ~/KaletaData/kaleta.db "VACUUM INTO '~/KaletaData/backups/kaleta-$(date +%F).db'"`
   into a cloud-synced dir). Do **not** rely on the in-app ZIP export yet
   (finding 1).
4. On upgrade: `git pull && uv sync &&
   KALETA_MIGRATE_URL=sqlite+aiosqlite:///$HOME/KaletaData/kaleta.db uv run alembic upgrade head`
   — *after* the daily backup ran.
5. Weekly: glance at `PRAGMA foreign_key_check` output until finding 3 is
   fixed.

## Acceptance criteria

- [x] Every P1 finding (5–10) converted into a draft plan:
  - P1.5 → [`currency-nbp-rates`](currency-nbp-rates.md)
  - P1.6 → [`planned-transactions-post-due`](planned-transactions-post-due.md)
  - P1.7 → [`import-bank-profiles`](../import-bank-profiles.md)
  - P1.8 → [`rules-auto-categorisation`](rules-auto-categorisation.md)
  - P1.9 → [`deploy-local-health`](deploy-local-health.md)
  - P1.10 → [`auth-reset-password-cli`](auth-reset-password-cli.md)
- [x] Every P0 finding converted into a GitHub issue / plan, added
  to the Chore inbox, or explicitly rejected with a note here
  (P0.1–0.3 covered by in-progress
  [`backup-full-schema-roundtrip`](backup-full-schema-roundtrip.md)
  and [`sqlite-integrity-scheduled-backups`](sqlite-integrity-scheduled-backups.md);
  P0.4 folded into [`migrate-on-startup`](migrate-on-startup.md) — all three
  now archived).
- [x] P2 items triaged (issue / Chore inbox / reject) — all addressed in
  [`p2-hardening-analysis`](p2-hardening-analysis.md) (archived).
- `[manual]` Interim runbook validated once by a real backup +
  restore drill (copy `.db`, open the copy via setup wizard,
  verify counts).

## Implementation

Landed on 2026-08-26.

This was a pure-audit plan: no production code changed. All findings were
converted into follow-up plans. The table below lists the originating
commits for the audit document itself.

| SHA | Author | Date | Message |
|---|---|---|---|
| `c605de0` | Dawid (Ani) | 2026-07-26 | docs: production-readiness audit (data-safety / operations lens) |
| `79f0131` | Dawid Adamski | 2026-07-27 | docs(plans): six draft plans for P1.5–10 audit findings (#33) |

**Follow-up plans that closed findings (all archived):**

| Finding | Plan | Status |
|---|---|---|
| P0.1 — backup table coverage + revision stamp | [`backup-full-schema-roundtrip`](backup-full-schema-roundtrip.md) | archived |
| P0.2 + P0.3 — scheduled VACUUM backups + SQLite pragmas | [`sqlite-integrity-scheduled-backups`](sqlite-integrity-scheduled-backups.md) | archived |
| P0.4 — auto-migrate on startup | [`migrate-on-startup`](migrate-on-startup.md) | archived |
| P1.5 — NBP currency rate fetch | [`currency-nbp-rates`](currency-nbp-rates.md) | archived |
| P1.6 — post due planned transactions | [`planned-transactions-post-due`](planned-transactions-post-due.md) | archived |
| P1.8 — rule-based auto-categorisation | [`rules-auto-categorisation`](rules-auto-categorisation.md) | archived |
| P1.9 — launchd/systemd doc + /health endpoint | [`deploy-local-health`](deploy-local-health.md) | archived |
| P1.10 — CLI password reset | [`auth-reset-password-cli`](auth-reset-password-cli.md) | archived |
| P2 — auth hardening, CSRF, API coverage, ledger export | [`p2-hardening-analysis`](p2-hardening-analysis.md) | archived |

**Remaining open item:**

- P1.7 — import profiles for real bank files → [`import-bank-profiles`](../import-bank-profiles.md) (active plan, not yet archived as of 2026-08-26)

**Acceptance criteria run** (step 3b): No executable acceptance criteria (all bullets are prose or `[manual]`).
