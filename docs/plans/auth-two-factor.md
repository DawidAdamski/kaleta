---
plan_id: auth-two-factor
title: Auth — two-factor authentication (TOTP + recovery codes)
area: auth / settings
effort: medium
status: in-progress
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

> **Deferred, not delivered.** Phase B is written against the `AuthProvider`
> interface from [`hosted-tenancy-foundation`](hosted-tenancy-foundation.md),
> which is still `draft`: `src/kaleta/auth/providers/` does not exist, and
> neither does any Supabase integration to hang `SupabaseAuthProvider` off.
> Building it would mean implementing another plan inside this branch, which
> Working Agreement §1 and the one-issue-one-branch-one-PR rule both forbid.
> Phase A ships on its own — the plan says so in its Intent — and Phase B
> moves to a follow-up plan once the foundation lands. Its acceptance
> criterion (`tests/unit/auth/test_supabase_mfa.py`) travels with it.

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

**Delivered: Phase A only.** See the note under Phase B — the hosted half
depends on an unimplemented plan and moves to a follow-up. Everything in
Phase A is built.

### Resolved open questions

1. **How is the TOTP secret protected before the encryption plan?**
   Plan default taken: derived from `KALETA_SECRET_KEY`, with
   `--disable-mfa` as the escape hatch. The derivation is HKDF-SHA256 →
   AES-256-GCM in `kaleta/db/types.py` (`EncryptedString`), a
   `TypeDecorator[str]` over `LargeBinary` with a format byte, a 12-byte
   nonce and the column's qualified name as AAD. The key comes from a
   module-level `_key_source`, swappable via `set_key_source()`, which is
   how `hosted-field-encryption` will drop its key ring in without
   touching the model. The reader already accepts format byte `\x00`
   (plaintext), so the `KALETA_ENCRYPTION=off` generation that plan
   describes will not orphan rows written now. Rotating
   `KALETA_SECRET_KEY` invalidates every enrolment; documented in
   `SECURITY.md` and `docs/tech-stack.md`.

2. **Step-up for API tokens only, or also account deletion / export /
   passphrase change?** API tokens only. The plan's guess was "likely all
   four", but "Delete my account" and a data passphrase do not exist yet
   (the passphrase arrives with `hosted-field-encryption`), and the
   export is a download rather than a credential that outlives the
   session. Listing four protected actions in the security-tab copy when
   only one is protected would be a lie in the UI, so the copy names
   none of them. The mechanism is reusable: `step_up_verified` is a
   keyword on the service method, so a fourth caller is one argument.

3. **Supabase `aal2` enforcement** — Phase B, deferred with it.

### Decisions a reviewer should know

- **`cryptography` became a base dependency**, alongside `pyotp` and
  `qrcode` which the plan's touchpoints name. Encrypting a column needs a
  cipher and the standard library has none; the alternative was hand-rolled
  crypto for a secret whose whole job is to be hard to steal.
  `hosted-field-encryption` §1 already declares `cryptography` "becomes a
  base dependency", so this is that plan's choice arriving one plan early
  rather than a new one. `types-qrcode` went into the dev group because
  `qrcode` ships no `py.typed` and mypy runs strict.

- **A pending session carries no `SESSION_AUTHENTICATED` at all.** Rather
  than teaching every guard about a new state, `begin_mfa_challenge()`
  stores the pending user under its own keys and leaves the authenticated
  flag unset. `is_authenticated()`, the UI middleware and
  `user_id_from_request()` (the API cookie path) therefore reject a
  half-finished login with no changes to any of them. `/login/mfa` is in
  `_PUBLIC_UI_PATHS` for the same reason and guards itself instead:
  no pending challenge, no page.

- **TOTP replay.** A code is valid for a whole 30-second step, which is
  long enough to read one off a shoulder and type it somewhere else.
  `last_used_counter` stores the accepted step and `_matching_counter()`
  refuses any step at or below it, so the drift window (±1 step) never
  becomes a reuse window.

- **`user_mfa` is in `db/audit.py`'s `_SKIP_TABLES`.** The audit listener
  serialises rows through the ORM, which would have copied the *decrypted*
  secret into `audit_log` in plain text — exactly what the encrypted
  column exists to prevent.

- **Password-stage `record_login(success=True)` is unchanged**, so the
  audit log still shows the password step separately from the factor.
  The audit events the module writes are `mfa_failure` (a wrong code or
  recovery code at the login prompt), `mfa_enrol_failure`,
  `mfa_disable_failure` (either half of the "turn it off" dialog) and
  `mfa_disabled_cli`. `_spend_recovery_code()` exists so that a recovery
  code used to disable is not logged as a login failure: the caller names
  the event, because a wrong code at a login prompt and a wrong code in
  the disable dialog are not the same thing to read back.

- **`--disable-mfa` writes an audit row per removed enrolment.** It is
  the one factor removal nobody had to prove anything to make, so it is
  the one that most needs a trace.

- **The e2e test is one test, not four.** Enrolment changes how every
  later login on the shared e2e instance behaves, so the whole life of a
  factor runs in one place behind a fixture that clears every enrolment
  before and after, whatever happened in between. `next_totp()` tracks the
  steps the test has spent and uses the drift window to get a fresh code
  without sleeping out a whole 30 seconds.

- **API bearer tokens are never challenged in use**, only when minted or
  revoked — they are a separate credential, as the plan says. There is a
  test pinning that (`test_bearer_authentication_is_untouched_by_mfa`).

- **New scenarios:** `KAL-AUTH-013`..`018` in `docs/bdd.md`, all
  `@automated`. 013–016 are covered by `tests/e2e/test_mfa.py`, 017 by
  `tests/integration/test_mfa_step_up.py`, 018 by
  `tests/integration/test_reset_password_cli.py`.
