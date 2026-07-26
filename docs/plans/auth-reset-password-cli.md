---
plan_id: auth-reset-password-cli
title: Auth — CLI password reset for single-user installs
area: auth
effort: small
status: draft
roadmap_ref: ../roadmap.md#q3-2026-jul-sep-stabilisation--debt
source: audit-production-readiness.md#10-password-reset-requires-hand-editing-the-database
---

# Auth — CLI password reset for single-user installs

## Intent

Single-user + argon2 with no CLI reset path: a forgotten password
means deleting the user row in SQLite so create-account bootstrap
reappears. Add `uv run kaleta --reset-password` (interactive) and
document it so recovery does not require hand-editing the database.

## Scope

- CLI flag on the `kaleta` entrypoint:
  `uv run kaleta --reset-password`
  - Resolves the configured DB (same path as the running app /
    `~/.kaleta/config.json`)
  - Prompts for new password (and confirmation) on stdin
  - Hashes with existing argon2 helpers in `AuthService`
  - Updates the sole user row; clear error if no user exists
    (point to create-account bootstrap) or if multiple users
    (unexpected — refuse)
- Document in getting-started and SECURITY (or equivalent): when
  to use the CLI vs wipe-user fallback
- Unit test for service `set_password` / reset path with temp DB
- BDD `KAL-AUTH-007` (CLI/unit — `@automated` via service test)

Additive to [`q3-auth-single-user.md`](q3-auth-single-user.md);
does **not** reopen session design, rate limits, or multi-user.

### Not in scope

- Email / magic-link reset
- In-UI "forgot password" flow
- Resetting API tokens as part of this command (optional note:
  tokens remain valid after password change unless separately
  revoked)
- Multi-user admin reset

## Acceptance criteria

- `uv run pytest tests/unit/services/test_auth_service.py -q`
- `grep -E 'KAL-AUTH-007' docs/bdd.md | grep -q .`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh`
- `[manual]` After changing the password via CLI, login with the
  new password succeeds and the old password fails.

## Touchpoints

- `src/kaleta/main.py` — argparse / CLI before `ui.run`
- `src/kaleta/services/auth_service.py` — `set_password` /
  `reset_password`
- `pyproject.toml` — entrypoint already `kaleta`; no new script
  required if flag lives on main
- `docs/` getting-started + SECURITY
- `docs/bdd.md` — `KAL-AUTH-007`
- `tests/unit/services/test_auth_service.py`

## Open questions

1. Non-interactive `--password-stdin` for scripting? Default: **not
   in v1**; interactive only (safer for local single-user).
2. Should reset also invalidate NiceGUI sessions / API tokens?
   Default: **document that existing sessions may linger until
   storage clear**; tokens unchanged.

## Implementation notes

_Filled in as work progresses._

Source finding: `audit-production-readiness` P1.10. One plan = one
branch = one PR. Can ship independently anytime (small).
