---
plan_id: auth-two-factor-hosted
title: Auth — two-factor authentication on the hosted instance (Supabase MFA)
area: auth
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#2027-directions
---

# Auth — two-factor authentication on the hosted instance (Supabase MFA)

## Intent

This is Phase B of [`auth-two-factor`](archive/auth-two-factor.md), carried out
of that plan rather than dropped from it. Phase A shipped the local TOTP
implementation: `MfaService`, the `user_mfa` table with its encrypted
secret, the `/login/mfa` prompt, the Settings card, recovery codes and
the `--disable-mfa` escape hatch. The hosted instance is supposed to get
the same second factor from Supabase Auth instead — enrolment,
verification and the `aal2` session claim handled by the identity
provider — with both halves behind one `AuthProvider` interface so no
view knows which is in play.

Phase B could not ship with Phase A because that interface does not
exist yet. It arrives with
[`hosted-tenancy-foundation`](archive/hosted-tenancy-foundation.md), which is
still `draft`: `src/kaleta/auth/providers/` is not a package, and there
is no Supabase integration for `SupabaseAuthProvider` to hang off.
Building both inside one branch would have meant implementing another
plan inside this one, which Working Agreement §1 and the
one-issue-one-branch-one-PR rule both forbid.

## Preconditions

- `hosted-tenancy-foundation` is implemented and merged, so that
  `src/kaleta/auth/providers/{base,local}.py` exist and the local path
  already runs through `AuthProvider`.

## Scope

- `SupabaseAuthProvider` implements `mfa_enrol()` (`/auth/v1/factors`),
  `mfa_challenge_verify(factor_id, code)` (`/factors/{id}/verify`) and
  `mfa_unenrol()`. After password sign-in GoTrue returns `aal1`; the
  provider reports `MfaRequired(factor_id)`, the same `/login/mfa` page
  collects the code, and on success the session is `aal2` and the access
  token is refreshed.
- Recovery codes: Supabase Auth does not issue them. Kaleta keeps its
  own (`recovery_codes_hash`, as in Phase A) and on a valid recovery
  code calls `mfa_unenrol()` with the service-role key, then forces
  re-enrolment at next login. The UI says so.
- The Settings card is the same component; the service behind it is
  chosen by the provider.
- Ordering on the hosted login: password → MFA → data passphrase
  (`/unlock`). Three prompts on a fresh device; the passphrase prompt is
  the one users meet most often after a restart, so its page explains
  why it is separate.
- Decide whether Supabase's `aal2` requirement needs enforcing on every
  request, or only at login and on token refresh. (Open question 3 of
  the Phase A plan, deferred here with its phase.)

## Not in scope

- Anything Phase A already delivered. The local TOTP path, the
  `user_mfa` table, `/login/mfa`, the Settings card and `--disable-mfa`
  are done and are not to be reworked here beyond what putting them
  behind `AuthProvider` requires.
- WebAuthn / passkeys, SMS or e-mail codes, `KALETA_MFA_REQUIRED`,
  trusted devices — all still out, as in Phase A.

## Touchpoints

`src/kaleta/auth/providers/{base,local,supabase}.py`,
`src/kaleta/views/login_mfa.py`, `src/kaleta/views/settings/security_tab.py`,
`src/kaleta/services/mfa_service.py`, `tests/unit/auth/test_supabase_mfa.py`
(new), `docs/bdd.md`.

## Acceptance criteria

- `uv run pytest tests/unit/auth/test_supabase_mfa.py -q` — the
  criterion carried over verbatim from `auth-two-factor`, which is why
  this file exists.
- `./scripts/verify.sh --e2e`
- [manual] On the hosted instance: enrol, sign out, sign in, and confirm
  the session reports `aal2` and that a recovery code forces
  re-enrolment.

## Open questions

1. Does `aal2` need checking on every request, or only at login and
   token refresh? Default if undecided: at login and on token refresh,
   matching where Phase A checks its own step-up.
2. Does a hosted account keep Kaleta-side recovery codes once Supabase
   owns the factor, or is account recovery handed to support? Default if
   undecided: keep them, as the Scope above describes — it is the
   behaviour Phase A's users already have.

## Implementation notes

- **Open question 1 (aal2 on every request?)** — default taken: checked at
  login only. `SupabaseAuthProvider.mfa_challenge_verify` refuses a verify
  whose token does not carry `aal: aal2`, and `SignInFlow.verify_code` is the
  only way a hosted MFA sign-in completes. "On token refresh" never happens:
  Kaleta keeps no GoTrue session (ADR-35 / `hosted-tenancy-foundation` — the
  provider session is ended right after sign-in), so there is no refresh to
  re-check at. Kaleta's own session is the session of record from there on,
  with Phase A's step-up window for sensitive acts.
- **Open question 2 (keep Kaleta-side recovery codes?)** — default taken:
  kept, in the same `user_mfa` row (`recovery_codes_hash`, as Phase A). A
  valid one at `/login/mfa` removes the GoTrue factor with the service-role
  key (`mfa_unenrol`, admin `DELETE /admin/users/{id}/factors/{id}`), and
  leaves the row with `enabled_at = NULL` and no codes. That row is the
  re-enrolment marker (`MfaService.reenrolment_required`): every sign-in while
  it stands lands on `/settings?tab=security` (`SignedIn.target`), whose card
  says why. "Forces re-enrolment" is therefore a forced landing plus a
  warning, not a hard gate in the middleware — a gate would block every page
  for an account that chose to stay password-only, which is a policy
  decision (`KALETA_MFA_REQUIRED`) this plan lists as out of scope.
- **No migration.** A hosted row is `kind = "supabase_totp"`
  (`MFA_KIND_SUPABASE`) and `totp_secret` holds GoTrue's factor id (still
  encrypted; it is an identifier). `MfaService._matching_counter` returns
  `None` for any non-`totp` row, so no local check ever computes a code from
  that id (pinned by a test that tries exactly that).
- **The password is asked again on the hosted card.** GoTrue's `/factors`
  endpoints need the user's JWT and Kaleta keeps none, so setup, step-up and
  turning off sign in with the password for the duration of the call
  (`HostedMfaService`). The card is the same component; the hosted dialogs
  carry a password field and their own hint strings.
- **The aal1 token between the password and the code** lives in
  `session.HostedMfaChallenges` (process memory, 10-minute TTL); the session
  store gets a random reference only (`test_session_contents` now drives this
  writer too). A restart forgets it — the prompt then says it took too long.
  Replicas need sticky sessions for `/login` and `/login/mfa` to meet, which
  NiceGUI's websocket already requires.
- **Magic links** now also return `MfaRequired` when a verified factor exists
  (`verify_magic_link -> Identity | MfaRequired`); before this, a magic link
  would have skipped the second factor once one existed.
- **Recovery codes are not taken at hosted step-up**: spending one removes the
  factor, which is the login prompt's decision. Someone without the
  authenticator recovers at sign-in, after which there is no factor left to
  step up with.
- **Disable timing.** Phase A balances password and code checks so the
  dialog is no password oracle; hosted, GoTrue refuses a wrong password
  before it looks at a code. Same message for both; the dialog limiter (5 /
  15 min) and GoTrue's `/token` rate limit bound it.
- **Audit**: hosted setup / step-up / disable / recovery write the same
  `mfa_*` auth events as Phase A plus `mfa_recovered`. A code checked at the
  hosted login prompt is recorded by GoTrue's audit log, not Kaleta's (the
  tenant is not resolved until the code is right); the sign-in itself is
  recorded by `SignInFlow` as before.
- **`/unlock` (the third prompt)** does not exist yet — it arrives with
  `hosted-field-encryption` (still `draft`). This plan puts MFA between the
  password and the session; the passphrase page and its "why separate"
  explanation belong to that plan.
- **`/settings?tab=<name>`** now opens the named tab, so the re-enrolment
  landing can point at Security.
- **BDD**: KAL-AUTH-036..039 `@automated` (integration
  `tests/integration/test_hosted_mfa.py`; provider HTTP shapes in
  `tests/unit/auth/test_supabase_mfa.py`). KAL-AUTH-040 `@planned` — the
  plan's manual criterion on a real Supabase project.
