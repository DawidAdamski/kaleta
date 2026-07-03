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

- Session backend: NiceGUI `app.storage.user` is already server-side —
  is its cookie signing sufficient, or do we add our own session table?
  (Investigate first; prefer building on NiceGUI storage.)
- Should `KALETA_MODE=api` support token-only (skip user bootstrap)?

## Implementation notes

(filled in as work progresses)
