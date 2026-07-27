---
plan_id: auth-reset-password-cli
title: CLI password reset for forgotten single-user credentials
area: auth
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
source: ../plans/audit-production-readiness.md#10-password-reset-requires-hand-editing-the-database
---

# CLI password reset for forgotten single-user credentials

## Intent

A forgotten password on a single-user Kaleta install currently forces
hand-editing (or deleting) the user row in SQLite so bootstrap reappears.
Ship an interactive `uv run kaleta --reset-password` that updates the
argon2 hash on the configured database — the same DB the running app
uses via `~/.kaleta/config.json`.

## Scope

- `uv run kaleta --reset-password`: prompt for new password + confirm;
  hash with argon2 via `AuthService`; resolve DB like the running app
  (`get_db_url()` / `~/.kaleta/config.json`, with `KALETA_DB_URL` only
  as the settings default when config is absent — match `_preload_config`).
- Clear errors: no user → point to first-run bootstrap; multiple users
  → refuse (single-user contract).
- Document in `docs/getting-started.md` and `SECURITY.md` (including that
  existing NiceGUI sessions may linger after a reset).
- BDD scenario `KAL-AUTH-007` + unit/integration tests.
- Interactive only in v1 (no `--password-stdin`).

### Not in scope

- Email-based password reset
- In-UI “forgot password”
- Multi-user admin / per-username selection
- Invalidating existing sessions or API tokens (document that sessions
  may linger until the browser storage is cleared or cookies expire)

## Acceptance criteria

- `uv run pytest tests/unit/services/test_auth_service.py tests/unit/cli/test_reset_password.py tests/integration/test_reset_password_cli.py -q`
- `grep -q 'KAL-AUTH-007' docs/bdd.md`
- `grep -q -- '--reset-password' docs/getting-started.md`
- `grep -q -- '--reset-password' SECURITY.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`

## Touchpoints

- `src/kaleta/main.py` — early `--reset-password` dispatch
- `src/kaleta/cli/reset_password.py` (new) — interactive command
- `src/kaleta/services/auth_service.py` — `reset_password` / user count
- `docs/bdd.md` — `KAL-AUTH-007`
- `docs/getting-started.md`, `SECURITY.md`
- `tests/unit/services/test_auth_service.py`
- `tests/unit/cli/test_reset_password.py` (new)
- `tests/integration/test_reset_password_cli.py` (new)

## Open questions

- None — interactive-only v1; sessions/tokens not revoked (documented).

## Implementation notes

- Plan file was missing from the repo at pickup; created from the audit
  finding + delivery brief, then implemented on `plan/auth-reset-password-cli`.
- DB resolution matches `_preload_config`: only `~/.kaleta/config.json` via
  `get_db_url()` — no silent fallback to CWD `KALETA_DB_URL` / `kaleta.db`.
- `AuthService.reset_password` enforces single real user (count 0 / >1 /
  placeholder → typed errors). Min length 8 shared via `validate_new_password`
  (also applied on `create_user` / `secure_placeholder` for consistency with UI).
- Interactive CLI only (`getpass`); no `--password-stdin`. Sessions/tokens not
  revoked — success message + SECURITY.md document the linger.
