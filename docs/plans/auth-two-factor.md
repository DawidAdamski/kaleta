---
plan_id: auth-two-factor
title: Auth — two-factor authentication (TOTP + recovery codes)
area: auth / settings
effort: medium
status: draft
roadmap_ref: ../roadmap.md#2027-directions
---

# Auth — two-factor authentication (TOTP + recovery codes)

## Intent

A password alone guards a ledger of someone's whole financial life.
Add a second factor: a time-based one-time code from an authenticator
app, plus one-time recovery codes for a lost phone. Self-hosted installs
get a local TOTP implementation; the hosted instance uses Supabase
Auth's MFA so enrolment, verification and the "AAL2" session claim are
handled by the identity provider. Both hide behind the `AuthProvider`
interface from [`hosted-tenancy-foundation`](hosted-tenancy-foundation.md),
and the local half ships first because it does not depend on that plan.

## Scope

### Phase A — local TOTP (independent of the hosted plans)

- **Model** `UserMfa` in the tenant schema: `user_id` (FK, unique),
  `totp_secret` (`EncryptedText` when
  [`hosted-field-encryption`](hosted-field-encryption.md) has landed,
  otherwise `String` encrypted with `KALETA_SECRET_KEY` via the same
  `TypeDecorator` under a static key — the type is written so the key
  source is swappable), `enabled_at`, `last_used_counter` (rejects
  replay of the same 30-second window), `recovery_codes_hash` (JSON list
  of argon2 hashes; each code is consumed on use). Alembic migration.
- **Service** `MfaService`: `begin_enrolment()` → secret + `otpauth://`
  URI + QR (`qrcode` renders it as an inline SVG; it is a small
  pure-Python dependency and goes into the base install), `confirm_enrolment(code)` (only then `enabled_at` is set),
  `verify(code)` with ±1 step drift, `generate_recovery_codes()` (10 ×
  10 chars, shown once), `consume_recovery_code(code)`, `disable(password)`.
  TOTP via `pyotp`.
- **Login flow** (`views/login.py`): after password success, if MFA is
  enabled the session is marked `SESSION_MFA_PENDING` and the user is
  routed to `/login/mfa` — six-digit field, "use a recovery code" link.
  The route guard treats a pending session as unauthenticated for every
  data page. Rate limiting reuses `LoginRateLimiter` keyed by
  `user_id` (5 wrong codes → 15 minutes), and each failure is written to
  the audit log as `mfa_failure`.
- **API tokens** are unaffected by MFA (they are a separate credential);
  creating or revoking a token while MFA is enabled requires a fresh
  code ("step-up") — `ApiTokenService` gets a `require_recent_mfa`
  check against `SESSION_MFA_VERIFIED_AT` (10-minute window).
- **CLI**: `kaleta.cli.reset_password` gains `--disable-mfa` for a locked-
  out self-hoster with shell access (the local equivalent of a recovery
  code, documented as such).
- **Settings → Security**: "Two-factor authentication" card — status,
  "Set up" (dialog: QR + manual secret + confirm code), "Show recovery
  codes" (regenerates, needs a fresh code), "Disable" (needs password +
  code). i18n `settings.mfa_*`.
- **Headless** (`KALETA_MODE=api`): MFA cannot be enrolled without the
  UI; the API exposes only status (`GET /api/v1/auth/mfa`).

### Phase B — hosted through Supabase Auth (after the foundation plan)

- `SupabaseAuthProvider` implements `mfa_enrol()` (`/auth/v1/factors`),
  `mfa_challenge_verify(factor_id, code)` (`/factors/{id}/verify`),
  `mfa_unenrol()`. After password sign-in GoTrue returns `aal1`; the
  provider reports `MfaRequired(factor_id)` and the same `/login/mfa`
  page collects the code; on success the session is `aal2` and the
  access token is refreshed.
- Recovery codes: Supabase Auth does not issue them. Kaleta stores its
  own (`recovery_codes_hash`, as in phase A) and on a valid recovery
  code calls `mfa_unenrol()` with the service-role key, then forces
  re-enrolment at next login. Documented in the UI.
- The Settings card is the same component; the service behind it is
  chosen by the provider.
- Ordering on the hosted login: password → MFA → data passphrase
  (`/unlock`). Three prompts on a fresh device; the passphrase prompt
  is the one users will meet most often after a restart, so its page
  explains why it is separate.

### Not in scope

- WebAuthn / passkeys (a later plan; the `UserMfa` table gets a `kind`
  column now so a second factor type is additive).
- SMS or e-mail codes.
- Enforcing MFA for every account (a per-instance
  `KALETA_MFA_REQUIRED` flag is a one-line follow-up once this exists).
- Trusted devices ("don't ask again for 30 days").

## Acceptance criteria

- `uv run pytest tests/unit/services/test_mfa_service.py -q` — enrol,
  confirm, verify with drift, replay rejected, recovery code consumed
  once, disable requires password
- `uv run pytest tests/unit/auth/test_mfa_guard.py -q` — pending session
  cannot reach data pages or `api/v1`
- `uv run pytest tests/e2e/test_mfa.py -q` — enrol via Settings, log
  out, log in with a generated code (test computes it with `pyotp`),
  log in with a recovery code, disable
- `uv run pytest tests/unit/auth/test_supabase_mfa.py -q` — provider
  against recorded `/factors` responses (Phase B)
- `uv run python scripts/spec_coverage.py`
- `grep -c "KAL-AUTH-" docs/bdd.md | grep -qE '^1[5-9]|^[2-9][0-9]'` —
  at least three new `KAL-AUTH-*` scenarios (enrol, verify, recovery)
- `./scripts/verify.sh --e2e`
- `[manual]` Enrol with Google Authenticator, 1Password and Aegis;
  confirm the QR scans and codes verify in all three.

## Touchpoints

`src/kaleta/models/user_mfa.py` (new), `alembic/versions/<new>_user_mfa.py`,
`src/kaleta/services/mfa_service.py` (new), `src/kaleta/services/api_token_service.py`,
`src/kaleta/auth/session.py` (`SESSION_MFA_PENDING`,
`SESSION_MFA_VERIFIED_AT`), `src/kaleta/auth/middleware.py`,
`src/kaleta/auth/login_rate_limit.py` (second limiter instance),
`src/kaleta/auth/providers/{base,local,supabase}.py`,
`src/kaleta/views/login.py`, `src/kaleta/views/login_mfa.py` (new),
`src/kaleta/views/settings/security_tab.py`, `src/kaleta/cli/reset_password.py`,
`src/kaleta/api/v1/auth.py` (new, status only), `src/kaleta/db/audit.py`
(auth event kinds), `src/kaleta/i18n/{en,pl}.json`, `pyproject.toml`
(`pyotp`, `qrcode`), `docs/bdd.md`, `docs/tech-stack.md`, `SECURITY.md`.

## Open questions

- Should the local `totp_secret` before the encryption plan be
  protected with `KALETA_SECRET_KEY` (rotating the key then breaks MFA
  for everyone) or stored plain in the SQLite file the self-hoster
  already owns? Recommendation: `KALETA_SECRET_KEY`-derived, with the
  `--disable-mfa` CLI as the escape hatch, and a note in
  `docs/tech-stack.md` that rotating the secret requires re-enrolment.
- Step-up for API-token management only, or also for "Delete my
  account", data export and passphrase change? Likely all four; list
  them in the security tab copy.
- Phase B only: does Supabase's `aal2` requirement need enforcing
  server-side on every request (check the JWT `aal` claim) or is the
  Kaleta session flag enough? The claim is authoritative; verify it
  once at login and again on token refresh.

## Implementation notes

(filled in as work progresses)
