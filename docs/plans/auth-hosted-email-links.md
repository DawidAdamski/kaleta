---
plan_id: auth-hosted-email-links
title: Auth — resend the confirmation e-mail, and sign in with a magic link (hosted)
area: auth
effort: medium
status: draft
roadmap_ref: ../roadmap.md#2027-directions
---

# Auth — resend the confirmation e-mail, and sign in with a magic link (hosted)

## Intent

Found in the manual run of
[`hosted-tenancy-foundation`](archive/hosted-tenancy-foundation.md) against a real
Supabase project: a person whose confirmation e-mail never arrived, or
expired, is told "Confirm your e-mail address first" and has no way to get a
new link — the only way out was confirming the user by hand in the Supabase
SQL editor. Separately, a hosted account has no password-less way in: a
"send me a sign-in link" button is the usual answer to a forgotten password
and is what Supabase Auth offers out of the box.

Both are two more GoTrue endpoints behind the `AuthProvider` interface that
`hosted-tenancy-foundation` introduces, plus a page each. Self-hosted
installs (`KALETA_AUTH_BACKEND=local`) have no mail and get neither.

## Preconditions

- `hosted-tenancy-foundation` is merged (it is, as #178): `AuthProvider`,
  `SupabaseAuthProvider`, `SignInFlow` and `tests/fake_gotrue.py` exist.

## Scope

### 1. Resend the confirmation e-mail

- `AuthProvider.resend_confirmation(email)`; `SupabaseAuthProvider` calls
  `POST /auth/v1/resend` with `{"type": "signup", "email": …}` and the same
  `redirect_to` as sign-up (`KALETA_PUBLIC_URL/login?reason=verified`).
  `LocalAuthProvider` raises `ValidationError` (no mail on a self-hosted
  install), like its password-reset methods.
- Login page: when sign-in fails with `EmailNotVerifiedError`, the message
  gains a "Resend confirmation e-mail" button that sends to the address in
  the e-mail field. The "check your inbox" state after sign-up gets the same
  button.
- The answer is the same whether or not the address exists or is already
  confirmed, and a GoTrue rate limit (`over_email_send_rate_limit`) reads as
  "a new link is on its way — if it does not arrive, wait a few minutes"
  rather than an error: the form must not reveal which addresses have
  accounts.
- Kaleta-side throttle: one resend per address per 60 seconds per process
  (the login rate limiter's store, so Redis covers replicas).

### 2. Sign in with a magic link

- `AuthProvider.request_magic_link(email)` → `POST /auth/v1/otp` with
  `{"email": …, "create_user": false}` and
  `redirect_to=KALETA_PUBLIC_URL/auth/magic`;
  `AuthProvider.verify_magic_link(token_hash) -> Identity` →
  `POST /auth/v1/verify` with `{"type": "magiclink", "token_hash": …}`,
  returning an `Identity` checked exactly like a password sign-in
  (`sub`/`email` claims against the user object).
- Login page: "E-mail me a sign-in link" under the password form; it sends
  to the address in the e-mail field and shows "check your inbox" (same
  no-enumeration answer as above).
- `/auth/magic?token_hash=…` page: verifies, then goes through
  `SignInFlow.complete` — so a first magic-link sign-in of a verified
  identity provisions the account, exactly like a first password sign-in —
  and `finish_login` with the usual session rotation. An expired or reused
  link lands on `/login?reason=link_expired`.
- Supabase "Magic Link" e-mail template pointing at
  `{{ .SiteURL }}/auth/magic?token_hash={{ .TokenHash }}`, documented in
  `docs/deployment.md` beside the reset-password template; the redirect URL
  added to the allow-list list there.
- `tests/fake_gotrue.py` learns `/resend` and `/otp`.

### Not in scope

- Creating an account from a magic link (`create_user: true`): sign-up stays
  e-mail + password, so the data-passphrase plan (`hosted-field-encryption`)
  has one entry point to hook.
- Magic links or e-mail codes as a *second* factor — MFA is
  [`auth-two-factor-hosted`](auth-two-factor-hosted.md). A magic-link
  session is `aal1` exactly like a password one; when that plan lands, it
  asks for the code after either.
- One-time e-mail *codes* (6-digit OTP typed into the page) instead of links.
- SMS, social logins, passkeys.
- Self-hosted installs.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_supabase_provider.py -q` — recorded
  GoTrue responses for `/resend`, `/otp` and `/verify` (magiclink), including
  the rate-limit and expired-link answers.
- `uv run pytest tests/e2e/test_tenant_signup.py -q` — resend after a lost
  confirmation e-mail, then confirm and sign in; magic-link sign-in to an
  existing account; an expired link is refused.
- `grep -q "KAL-TEN-006" docs/bdd.md` — resend confirmation.
- `grep -q "KAL-TEN-007" docs/bdd.md` — magic-link sign-in.
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`
- `[manual]` Against a real Supabase project: sign up, ignore the first
  e-mail, resend, confirm from the second one; sign out; sign in with a
  magic link.

## Touchpoints

`src/kaleta/auth/providers/{base,local,supabase}.py`,
`src/kaleta/auth/login_rate_limit.py` (resend throttle),
`src/kaleta/views/login.py`, `src/kaleta/views/create_account.py`,
`src/kaleta/views/magic_link.py` (new), `src/kaleta/auth/middleware.py`
(public path `/auth/magic`), `src/kaleta/main.py`,
`src/kaleta/i18n/locales/{en,pl}.json`, `tests/fake_gotrue.py`,
`tests/unit/auth/test_supabase_provider.py`,
`tests/e2e/test_tenant_signup.py`, `docs/bdd.md`, `docs/deployment.md`.

## Open questions

1. Should a magic link be able to create an account? Default: no
   (`create_user: false`) — see Not in scope.
2. Is the Kaleta-side resend throttle worth having when GoTrue already
   rate-limits e-mail? Default: yes, 60 s per address — GoTrue's limit is
   project-wide (a few e-mails per hour on the built-in mailer), so one
   impatient person would otherwise use it up for everyone.
3. Where does the "E-mail me a sign-in link" button sit on artboard `3f`?
   Default: a quiet `auth_link`-style line under the submit button, beside
   "Forgot password?", so the password form stays the primary action.

## Implementation notes

_Filled in as work progresses._
