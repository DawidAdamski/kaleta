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
> moves to [`auth-two-factor-hosted`](auth-two-factor-hosted.md), which
> carries everything below and the acceptance criterion
> (`tests/unit/auth/test_supabase_mfa.py`) with it, to be picked up once
> the foundation lands.

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
`src/kaleta/views/login.py`, `src/kaleta/views/login_mfa.py` (new),
`src/kaleta/views/settings/security_tab.py`, `src/kaleta/cli/reset_password.py`,
`src/kaleta/api/v1/auth.py` (new, status only), `src/kaleta/db/audit.py`
(auth event kinds), `src/kaleta/i18n/{en,pl}.json`, `pyproject.toml`
(`pyotp`, `qrcode`, `cryptography`), `src/kaleta/db/types.py` (new),
`src/kaleta/services/backup_service.py`, `docs/bdd.md`,
`docs/tech-stack.md`, `SECURITY.md`, `docs/adr/036-*.md`.

Deferred to the Phase B follow-up along with Phase B itself:
`src/kaleta/auth/providers/{base,local,supabase}.py` and
`tests/unit/auth/test_supabase_mfa.py`.

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
depends on an unimplemented plan and moves to a follow-up. Every Phase A
item is built, and every executable acceptance criterion passes.

**Open for the owner, not closed here:**

- The `[manual]` criterion — enrol with Google Authenticator, 1Password
  and Aegis and confirm the QR scans and the codes verify in all three.
  Nothing in this branch can run it; three real authenticator apps have
  to be held in a hand. The `otpauth://` URI is standard and
  `tests/e2e/test_mfa.py` scans nothing, so this is the one check that
  the QR itself is right.
- **Ratifying the Phase B deferral.** This branch edits its own scope
  contract: it takes
  `uv run pytest tests/unit/auth/test_supabase_mfa.py -q` out of the
  acceptance criteria and the `auth/providers/` files out of Touchpoints,
  and says under Phase B where they go. The reasoning is in that block
  quote, but removing a criterion is the owner's call, not the
  implementer's. So that the criterion is moved rather than lost, the
  follow-up now exists as a file:
  `docs/plans/auth-two-factor-hosted.md` (`status: draft`) carries
  Phase B's scope and that same acceptance criterion. A draft plan is
  not a commitment to schedule it — that, and whether the deferral was
  the right call at all, is still the owner's to say on the PR.

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
   none of them. The mechanism is reusable: `mfa_verified_at` is a
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
  `mfa_disabled_cli`, `mfa_step_up_failure`, each of them asserted in
  `TestTheAuditTrail`. `_spend_recovery_code()` exists so that a recovery
  code used to disable is not logged as a login failure: the caller names
  the event, because a wrong code at a login prompt and a wrong code in
  the disable dialog are not the same thing to read back.

- **Nothing on the way back from a rotated key decrypts anything.**
  `begin_enrolment()` included: an unconfirmed row abandoned in a closed
  tab before a rotation would otherwise make the Set up button fail for
  good, with no enabled factor anywhere to explain why. It reads two
  columns and overwrites in place.
  `SECURITY.md` points a locked-out self-hoster at
  `kaleta --reset-password --disable-mfa`, so that path has to work when
  every secret in the table is unreadable. `is_enabled()` and `status()`
  select single columns rather than loading the row — otherwise the
  *password* step of every login would raise, for everybody — and
  `disable_all()` reads `user_id` and issues a bulk `DELETE` rather than
  loading ORM objects. The CLI removes the enrolments **before** it
  changes the password, so a failure leaves nothing changed instead of a
  new password and the old lockout. `/login/mfa` catches
  `EncryptionError` and names the command, rather than failing forever
  with no reason given. Four tests in `TestAfterAKeyRotation` and one in
  `test_reset_password_cli_works_after_a_key_rotation` hold that shut.

- **The throttle stays in the views, as `login.py` already does it.** The
  service says in its docstrings that it counts nothing and the caller
  must; moving `LoginRateLimiter` down a layer would mean rewriting the
  password login's throttle in the same diff, which rule 9 rules out.
  One for the Chore inbox.

- **The replay guard is a conditional `UPDATE`, not a read-then-write.**
  Two tabs holding the same code both passed `_matching_counter` before
  either committed, which is precisely the replay the counter exists to
  stop; a recovery code could be spent twice the same way. Both are now
  claimed with an `UPDATE ... WHERE` on the value that was read, and a
  `rowcount` of zero is a loss. `TestConcurrentSubmits` runs the race
  with two sessions. Every other write in the module claims the same way
  and for the same reason: `confirm_enrolment()` (two tabs confirming one
  pending enrolment both won, and the second overwrote the ten codes the
  first had already shown its user), `regenerate_recovery_codes()` (the
  same, for a reissue), and `begin_enrolment()`'s overwrite of an
  unconfirmed row (a confirmation landing in the gap would have left the
  row enabled, holding a secret nobody has and no recovery codes —
  locked out of a factor that says it is on).

- **`--disable-mfa` writes an audit row per removed enrolment.** It is
  the one factor removal nobody had to prove anything to make, so it is
  the one that most needs a trace.

- **A sign-in is now two rows, and the reader of the log has to know it.**
  `views/login.py` still calls `record_login(success=True)` when the
  password is accepted, which is the moment it is accepted and not the
  moment the session is signed in — between them lies `/login/mfa`, which
  the visitor may fail or walk away from. Rather than move that row (it
  is what the login rate limiter and every existing `KAL-AUTH` scenario
  are written against), the second half says so: `verify_code()` and
  `consume_recovery_code()` write `mfa_verified` on success. A finished
  sign-in is `login` followed by `mfa_verified`; a `login` with no
  `mfa_verified` after it is a password that was right and a factor that
  was never proved, which is exactly the pattern worth looking for.

- **Three messages the happy path never shows got scenarios, not tests.**
  `KAL-AUTH-021` (the challenge ages out), `KAL-AUTH-022` (the factor is
  turned off in another tab while the prompt is open) and `KAL-AUTH-023`
  (the secret was written under a different `KALETA_SECRET_KEY`) are all
  `@manual`. Each needs something the e2e harness cannot stage against
  its own ephemeral instance — ten minutes of wall clock, a second
  browser context racing the first, or a key rotation between two
  requests — and tagging them `@automated` on the strength of the unit
  tests underneath would be the green-washing rule 4 forbids. The
  service-level halves *are* covered: `verify_code()` returning False on
  a disabled factor, and `EncryptionError` surfacing out of the column
  type.

- **A factor turned off mid-prompt is not a wrong code.** `verify_code()`
  answers False whether the code was wrong or the row is gone, and
  `/login/mfa` used to charge both to the same five-try limiter — so
  turning two-factor off in one tab could lock the other tab out of a
  login that had just become password-only. The page now asks
  `is_enabled()` first and redirects to `/login?reason=mfa_gone`, whose
  copy says the password is now all that is needed. `verify_code()` keeps
  its plain bool: the tri-state belongs to the one caller that can act on
  it, not to every caller.

- **Every prompt that counts a failure asks the same question first.**
  `verify_code()`, `verify_challenge()` and `confirm_enrolment()` each
  fold "the row is gone" into the answer they give for "that was wrong",
  and all three callers charge that answer to `mfa_rate_limiter` — the
  single bucket that guards the login prompt. So a factor dropped from a
  shell, or turned off in another tab, could lock someone out of a login
  that had just become password-only, for a failure they had no way to
  avoid. Fixed in all three: `/login/mfa` and the step-up dialog ask
  `is_enabled()` before submitting, and `confirm_enrolment()`'s missing
  pending row is now a `ConflictError` rather than a `ValidationError`
  (nothing was wrong with what was typed), which the setup dialog already
  leaves uncounted.

- **The dialogs' own errors are localized; the fallback is not.** The
  three two-factor dialogs used to print `exc.message` — the service's
  English literal — beside labels that all went through `t()`, so a
  Polish user met mixed-language copy on the most common error of all.
  `ValidationError`, `ConflictError` and `EncryptionError` now map to
  `settings.mfa_{enrol_failed,disable_failed,stale,unreadable}` in both
  locales. The turn-off dialog keeps one message for both halves, as the
  service gives it: naming which half was wrong would make it a password
  oracle. The bare `except KaletaError` fallback still shows
  `exc.message`, which is the `notify_kaleta_error` convention for a
  domain error no view anticipated — by then the copy being English is
  the smaller problem.

- **`_safe_redirect` was copied into the new page, and is now shared.**
  `views/login_mfa.py` began as a copy of `views/login.py`'s guard, which
  let `/\evil.com` through — a browser normalises the backslash, so that
  is the protocol-relative URL the `//` check was written to stop, wearing
  a different hat. Rather than fix one copy and leave two that disagree,
  the guard moved to `views/auth_common.py` as `safe_redirect()`, tightened
  to reject both, with `tests/unit/views/test_safe_redirect.py` over it.
  Rule 9 would normally send the pre-existing half to the Chore inbox;
  it is here because this branch is what duplicated it, and a shared
  helper is the only version of this fix that does not leave a second
  copy to drift.

- **Every conditional UPDATE reads its verdict before the commit.**
  `rowcount` is memoized off a cursor that committing closes, and the
  `or 0` fallback would read an unavailable count as "somebody else got
  there first" — a spurious conflict on a write that actually landed.
  Four of the five claim sites read it after. They now all go through
  `MfaService._claimed()`, which is the one place that knows the rule.
  SQLite never showed the fault; asyncpg is where it would have.

- **`safe_redirect` judges the string the browser will see.** Rejecting
  `//` and `/\` is not enough: the WHATWG URL parser removes tab, LF and
  CR before anything else reads the URL, so `?redirect_to=/%09/evil.com`
  arrives as `/\t/evil.com`, passes a raw-string check, and leaves
  `ui.navigate.to()` as `//evil.com`. The guard now strips those three
  characters first and judges what is left — which is also what it
  returns. The `RedirectResponse` paths were never exposed (Starlette
  percent-quotes `Location`); the post-login `ui.navigate.to()` was.

- **Turning the factor off is a claim too.** `disable()` was the one
  mutation in the module still using `session.delete(row)`, so two tabs
  turning it off at once — or a `--disable-mfa` landing mid-dialog —
  raised `StaleDataError` out of the unit of work, which no dialog has an
  arm for. It is now a conditional DELETE through `_claimed()`, and the
  loser gets the same `ConflictError` every other contended write gives.

- **Successes are audited, not only failures.** `user_mfa` is in
  `db/audit.py`'s `_SKIP_TABLES` — auditing it would copy the decrypted
  secret into `audit_log` — so the generic ORM listener sees none of
  this, and anything the service does not write itself is not written.
  `confirm_enrolment()` writes `mfa_enabled`, `disable()` writes
  `mfa_disabled`, and `verify_challenge()` writes `mfa_step_up` —
  deliberately a different event from the login prompt's `mfa_verified`,
  because that is the answer that unlocks minting a bearer token
  outliving the session, and a recovery code spent there is crossed off
  for good. Turning the factor off is the step a thief at a
  signed-in browser has to take, and a log holding only the codes they
  fumbled on the way is a log that recorded the noise and missed the
  theft.

- **Two files the plan did not foresee changed, and had to.** They are in
  the Touchpoints list above because this branch put them there;
  everything below is why.
  `src/kaleta/services/backup_service.py` and `tests/backup_helpers.py`:
  an encrypted column is a `LargeBinary`, and a `LargeBinary` is not
  JSON, so the export failed outright the moment `user_mfa` existed.
  Binary columns now travel as base64 and are restored as the ciphertext
  they are — the restore never decrypts, so a backup carries no readable
  secret, and re-encrypting on the way back in would have turned a
  restored secret into noise that still looked like a row. A backup made
  before `KALETA_SECRET_KEY` was rotated cannot be read after it, which
  is the same trade the key derivation already makes.
  `KAL-SET-015` gained a line about values, not just row counts, and
  `test_restore_preserves_an_encrypted_secret` covers it.

- **`KAL-AUTH-019` and `KAL-AUTH-020`** were added for reissuing recovery
  codes and for turning the factor off, both of which the e2e test walks
  through. `KAL-AUTH-017` lost a line claiming the step-up prompt is
  rate-limited: it is, but the prompt only appears once the ten-minute
  window has passed, which no test can reach without waiting it out. The
  throttle is asserted where it is reachable — the turn-off dialog, which
  always asks — and it is the same limiter on the same key.

- **`EncryptedString` takes its AAD as an ordinary positional-or-keyword
  argument and keeps it on a public attribute.** SQLAlchemy builds a
  `TypeDecorator`'s static cache key from the constructor arguments it can
  see on the instance, skipping keyword-only and underscored ones — so
  either of those spellings would have made the declared `cache_ok = True`
  a lie as soon as `hosted-field-encryption` adds a second encrypted
  column, and two types that must not share a bind processor would have
  looked identical to the statement cache. A test pins it.

- **`ADR-36` records the local encryption format** and the three new base
  dependencies, as `docs/review-checklist.md` asks when the
  dependencies-of-record change. It is written so `ADR-35`'s key ring
  replaces the key source rather than the format.

- **The step-up window is the service's judgement, not the view's.** The
  plan says `ApiTokenService` checks `SESSION_MFA_VERIFIED_AT`, but a
  service that reads `app.storage.user` would import NiceGUI. So the view
  passes `mfa_verified_at()` — a timestamp, not a verdict — and
  `MfaService.step_up_is_fresh()` owns the 10-minute window. A caller
  cannot widen it by asserting that it checked.

- **The code limiter is keyed by user id, as the plan asks, and that has
  a cost worth naming:** anyone who knows the password can burn five
  wrong codes and keep the real owner out of the code prompt — and out
  of token management — for fifteen minutes at a time. Keying by IP
  instead would let an attacker with a botnet walk past the limit
  entirely, which is worse; the lockout is the cheaper of the two
  failures, and `SECURITY.md` says so. The limiter itself is
  `LoginRateLimiter`, whose five-in-fifteen-minutes behaviour
  `KAL-AUTH-008` already pins; what `KAL-AUTH-020` adds is that the
  dialogs are wired to it. The login prompt's own wiring is the same two
  lines against the same object, and is not separately asserted — the
  e2e test cannot burn five codes there without locking the account for
  the rest of the run. One bucket covers all three prompts, so wrong
  answers in the turn-off dialog lock the code prompt too; `SECURITY.md`
  says so, and so does the e2e fixture, because the test ends with the
  e2e user locked for fifteen minutes and a reused server would carry
  that into the next run.

- **A pending challenge expires** after `MFA_CHALLENGE_TTL_MINUTES`.
  A browser left at the code prompt was otherwise one code away from a
  login for as long as the session lasted.

- **The "turn it off" dialog answers wrong password and wrong code with
  the same sentence**, weighs both halves before judging either, and is
  throttled on the same counter as the login prompt. Telling the two
  apart made it a password oracle that answered without going past
  `login_rate_limiter` — and returning early on a wrong password left
  the same oracle in the timing, because a right password went on to run
  up to ten more argon2 verifies against the recovery hashes. The
  recovery scan runs whatever the TOTP check said, so the reply does not
  time differently depending on the password. It does still time
  differently depending on the *code* — a matching recovery code is found
  after however many hashes it took — and that residue is priced rather
  than bought off: fifty bits a code, five tries a quarter of an hour, and
  the alternative is ten argon2 verifies on every attempt including the
  ones that work. Nothing is spent unless both halves are right. "Not enabled" is a `ConflictError`,
  not a `ValidationError`, so a stale dialog does not count toward the
  lockout.

- **The code prompt re-reads the challenge when the code is submitted.**
  Checking only at page load meant the TTL applied to a reload and to
  nothing else: a prompt left open past it, or one whose session was
  logged out in another tab, still signed in on one code.

- **`regenerate_recovery_codes()` enforces step-up itself**, the same way
  `ApiTokenService` does. Ten fresh codes are ten fresh ways past the
  factor, and the plan puts that rule on the feature, not on the one view
  that happens to call it today.

- **The ciphertext passthrough on `EncryptedString` is narrow.** It takes
  only blobs that start with the AES-GCM format byte. An unrestricted
  one would have made `b"\x00" + secret` a way to write a plaintext
  value that the reader accepts.

- **The two new CLI integration tests carry no `skipif`.** The two older
  tests in that file skip under postgres because `ResetPasswordCli`
  repoints the shared session factory at its own SQLite file and never
  puts it back. A `global_db_restored` fixture restores it instead, which
  is what the skip was standing in for, and the flag stays covered on
  both backends.

- **The e2e test is one test, not four.** Enrolment changes how every
  later login on the shared e2e instance behaves, so the whole life of a
  factor runs in one place behind a fixture that clears every enrolment
  before and after, whatever happened in between. `next_totp()` tracks the
  steps the test has spent and uses the drift window to get a fresh code
  without sleeping out a whole 30 seconds.

- **API bearer tokens are never challenged in use**, only when minted or
  revoked — they are a separate credential, as the plan says. There is a
  test pinning that (`test_bearer_authentication_is_untouched_by_mfa`).

- **New scenarios:** `KAL-AUTH-013`..`020` in `docs/bdd.md`, all
  `@automated`. 013–016, 019 and 020 are covered by
  `tests/e2e/test_mfa.py`, 017 by `tests/integration/test_mfa_step_up.py`,
  018 by `tests/integration/test_reset_password_cli.py`. `KAL-SET-015`
  gained a line and `tests/integration/test_backup.py` covers it.
