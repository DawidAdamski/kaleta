---
plan_id: auth-two-factor-hosted
title: Auth — two-factor authentication on the hosted instance (Supabase MFA)
area: auth
effort: medium
status: draft
roadmap_ref: ../roadmap.md#2027-directions
---

# Auth — two-factor authentication on the hosted instance (Supabase MFA)

## Intent

This is Phase B of [`auth-two-factor`](auth-two-factor.md), carried out
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
[`hosted-tenancy-foundation`](hosted-tenancy-foundation.md), which is
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
