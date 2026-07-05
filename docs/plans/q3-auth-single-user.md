---
plan_id: q3-auth-single-user
title: Single-user authentication — sessions, API tokens, secure defaults
area: auth
effort: large
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
---

# Single-user authentication — sessions, API tokens, secure defaults

## Intent

Kaleta currently has no authentication and binds `0.0.0.0` by default:
anyone on the LAN can read and modify financial data. Auth is also the
hard prerequisite for the open-source release and any commercial tier.
This plan delivers single-user auth designed so multi-user (2027) is a
migration, not a rewrite.

## Scope

- `User` model (id, username, password_hash, created_at) + Alembic
  migration. Passwords hashed with argon2 (`argon2-cffi`).
- **Forward-compatible ownership:** add `user_id` FK to user-owned
  tables (accounts, categories, transactions, budgets, payees,
  planned/recurring, credit profiles, assets, reserve funds, tags,
  reports, subscriptions, personal loans …) in one migration; backfill
  everything to the single user. Services keep their current
  signatures — a session-scoped `current_user_id` dependency supplies
  the value.
- Login page (NiceGUI) + server-side session; first-run: if no user
  exists, the setup wizard's first step creates one (or
  `KALETA_ADMIN_PASSWORD` env var for headless installs).
- Route guard: every UI page and every `api/v1` route requires auth;
  PWA/static assets and `/login` are exempt.
- API bearer tokens: `ApiToken` model (hashed token, label,
  created/last-used, revoked), management UI in Settings → Data or a
  new Security tab; `Authorization: Bearer` accepted by `api/deps.py`.
- Secure defaults: default host `127.0.0.1` in web mode (Docker
  compose explicitly sets `0.0.0.0`); refuse to start with the
  placeholder `KALETA_SECRET_KEY` unless `KALETA_DEBUG=true`; audit
  log records login success/failure and token create/revoke.
- e2e: add `login()` helper to the suite from `q3-test-safety-net`;
  add scenarios: login, wrong password, API 401 without token.
- **Not in scope:** multi-user UI, roles/permissions, OAuth/passkeys,
  password reset by email, rate limiting (note as follow-up).

## Acceptance criteria

- Fresh install forces creating a password before any data page loads.
- Unauthenticated → UI redirects to `/login`; API returns 401 JSON.
- All API integration tests updated and green (token fixture).
- App refuses to start with default secret key outside debug mode.
- Docs updated: README (quick start includes first-run password),
  `docs/tech-stack.md` env vars table.

## Touchpoints

`src/kaleta/models/user.py`, `api_token.py` (new), migration(s),
`src/kaleta/config/settings.py`, `main.py` (middleware/guard),
`api/deps.py`, `views/login.py` (new), `views/settings.py`,
`db/audit.py`, `scripts/seed.py`, tests across all suites, README,
`docs/tech-stack.md`.

## Open questions

- ~~Should `KALETA_MODE=api` support token-only (skip user bootstrap)?~~ **Resolved** — see notes below.

## Implementation notes

### Session backend (sub-task 2)

**Decision:** Use NiceGUI `app.storage.user` as the sole session store — no
custom session table.

**Investigation:** NiceGUI wires `storage_secret` (Kaleta: `KALETA_SECRET_KEY`)
into Starlette `SessionMiddleware`, which signs an HTTP-only session cookie and
maps it to per-client server-side storage. Kaleta already passes
`storage_secret=settings.secret_key` in `ui.run()`. Auth state
(`authenticated`, `user_id`, `username`) lives in that store alongside existing
preferences (dark mode, dashboard layout, etc.). This matches NiceGUI's
[official authentication example](https://github.com/zauberzeug/nicegui/blob/main/examples/authentication/main.py).

**Why sufficient for single-user v1:** Session fixation/tampering is mitigated
by signed cookies; idle timeout is acceptable for a self-hosted LAN app (no
server-side TTL today — follow-up if needed). Logout clears `app.storage.user`
auth keys. API bearer tokens (sub-task 3) will be separate credentials, not
cookie sessions.

### UI auth (sub-task 2)

- **Session store:** `app.storage.user` keys `authenticated`, `user_id`, `username`.
- **Guard:** `AuthMiddleware` in `kaleta/auth/middleware.py` — registered from
  `main.py` before views. Exempt: `/login`, `/create-account`, `/secure-app`,
  `/setup`, PWA/static, `/_nicegui`, `/api/v1/*` (API guard deferred to sub-task 3).
- **Bootstrap:** fresh DB → `/create-account`; placeholder user → `/secure-app`;
  after DB setup wizard activates a DB, redirect follows the same rules.
- **Audit:** `record_auth_event()` in `db/audit.py` (`operation=AUTH`); login
  success/failure and logout via `AuthService.record_login` / `record_logout`.

### Data model (sub-task 1)

**Tables that received nullable `user_id` FK → `users.id`:**

| Table | Notes |
|-------|-------|
| `accounts` | |
| `categories` | |
| `transactions` | |
| `budgets` | |
| `payees` | |
| `planned_transactions` | planned/recurring |
| `credit_card_profiles` | credit profiles |
| `loan_profiles` | credit profiles |
| `assets` | |
| `reserve_funds` | |
| `tags` | |
| `saved_reports` | reports |
| `subscriptions` | |
| `counterparties` | personal-loan counterparties |
| `personal_loans` | |

**Not given `user_id` in this migration** (global / child / deferred):
`institutions`, `transaction_splits`, `transaction_tags`,
`personal_loan_repayments`, `yearly_plans`, `monthly_readiness`,
`dismissed_candidate_patterns`, `currency_rates`, `audit_log`.

**Migration behaviour:** `d8f1a2b3c4e6` creates `users`, adds nullable
`user_id` to the tables above, and — only when the database already holds
user-created rows (not merely Alembic seed tags/categories) — inserts a
`__placeholder__` user and backfills all rows. Fresh full-migration installs
get no user row; the setup wizard creates the real user in sub-task 2.

**Migration verification:** copied `kaleta.db` (pre-migration, seed-only rows),
inserted a test account to simulate an existing install, recorded row counts,
ran `alembic upgrade head` (placeholder created, `user_id` backfilled), then
`downgrade -1` → `upgrade head` — counts unchanged, account still owned by
`__placeholder__`. Confirmed seed-only and full fresh-migration installs get
zero `users` rows.

### API bearer tokens + secure defaults (sub-task 3)

**`KALETA_MODE=api` bootstrap:** `KALETA_API_TOKEN` env var is accepted as a
bearer token without a database row. It authenticates as the single non-placeholder
user when one exists. Headless API deployments set this once; UI-managed tokens
(`api_tokens` table) remain the normal path for `web`/`app` mode.

**API guard:** `require_api_auth` on `v1_router` in `api/v1/__init__.py`.
`get_current_user_id` in `api/deps.py` accepts `Authorization: Bearer` (SHA-256
hash lookup + `secrets.compare_digest`, updates `last_used_at`) or an authenticated
NiceGUI session cookie via `user_id_from_request()`. Unauthenticated requests get
401 `{"detail": {"error": "unauthorized", ...}}`.

**Secure defaults:** default `KALETA_HOST=127.0.0.1` (Docker Compose sets
`0.0.0.0`); placeholder `KALETA_SECRET_KEY` refused when `KALETA_DEBUG=false`
(already in `settings.py`); `/setup` exempt only when DB is not yet configured
(first-run wizard stays public).

**Settings UI:** new Security tab — create token (label + one-time copy dialog),
list tokens, revoke; audit `AUTH` rows on create/revoke (`table_name=api_token`).

**Acceptance criteria (sub-task 3 final check):**

| Criterion | Result |
|-----------|--------|
| Fresh install forces password before data pages | **PASS** (sub-task 2: `/create-account` bootstrap) |
| Unauthenticated UI → `/login`; API → 401 JSON | **PASS** (`AuthMiddleware` + `require_api_auth`) |
| All API integration tests green with token fixture | **PASS** (`api_client` + `api_bearer_token`) |
| App refuses default secret key outside debug | **PASS** (`Settings._validate_secret_key`) |
| Docs updated (README, tech-stack) | **PASS** |
