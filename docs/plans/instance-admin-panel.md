---
plan_id: instance-admin-panel
title: Instance admin panel — families, registration mode, password resets
area: auth / settings
effort: medium
status: in-progress
roadmap_ref: ../roadmap.md#2027-directions
---

# Instance admin panel — families, registration mode, password resets

## Intent

Whoever runs a Kaleta instance — a parent on a homelab, or the maintainer
for the hosted one — needs to create families, decide who may sign up,
help someone who forgot their login password, and suspend or delete a
family, without a terminal. Today all of it is `kaleta-admin` (`kaleta.cli.tenant_admin`).
Put the same operations behind a page only the instance administrator
sees, showing nothing the operator may not see (ADR-35: e-mails, counts,
statuses — never financial data).

Depends on [`postgres-only`](archive/postgres-only.md) (instance admin,
`local_identities`, `registration_mode`).

## Delivery

Two pull requests (decided 2026-10-11 after mapping the code), each green on
its own:

- **A — the service, the audit and the CLI** (no views):
  `InstanceAdminService` with every operation of the panel, the registry's
  `admin_audit` table, `must_change_password` set by a reset, and
  `kaleta-admin` running through the same service (and so audited).
- **B — the panel**: `/admin`, the navigation entry, the step-up, the
  forced password change at the next sign-in, the e2e scenarios.

## Scope

- `/admin`, visible in the navigation only to an identity with
  `is_instance_admin`; every route and service call re-checks the flag
  (a member who types the URL gets 404, not a disabled page).
- **Families**: table of name, owner e-mail, member count / limit,
  status (`active`, `suspended`, `pending`), created, last seen. Actions:
  create (name + owner e-mail; the owner gets a one-time password shown
  once to the admin, or an e-mail when SMTP is configured), suspend,
  resume, delete (typed confirmation of the family name, then
  `AccountDeletionService`). Same services as `tenant_admin.py`.
- **Registration**: `closed` / `invite` / `open`, with one sentence
  explaining each; `open` on a `local` instance warns that anyone who
  reaches the URL can create a family.
- **Identities** (`local` backend only): list, disable/enable, reset
  password (one-time password shown once; the user must change it at the
  next sign-in), revoke sessions. With `supabase` this section says the
  identities live in Supabase.
- **Instance**: version, migration head, family count, member limit
  (`KALETA_HOUSEHOLD_MAX_MEMBERS`), last start — read-only.
- Audit: every admin action writes one line to a registry
  `admin_audit` table (admin id, action, family id, timestamp — no
  e-mail of the target) and to the log.
- Admin actions need a fresh password (and TOTP when enrolled) once per
  15 minutes (`step-up`, as account deletion does).
- BDD scenarios `KAL-ADM-001…`; e2e for create family → owner signs in,
  suspend → owner refused, registration `closed` → no sign-up link.

### Not in scope

- Reading or exporting a family's data (the operator never can).
- Invites, approval and re-keying inside a family
  ([`hosted-household-sharing`](hosted-household-sharing.md)).
- Billing or plans.

## Acceptance criteria

- `uv run pytest tests/integration/test_instance_admin_service.py -q`
- `uv run pytest tests/e2e/test_instance_admin.py -q`
- `grep -q "KAL-ADM-001" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `./scripts/verify.sh --e2e`

## Touchpoints

`src/kaleta/views/admin.py` (new), `src/kaleta/views/layout.py` (nav),
`src/kaleta/services/instance_admin_service.py` (new),
`src/kaleta/services/tenant_service.py`,
`src/kaleta/auth/account_deletion.py`, `alembic_public/versions/` (new:
`admin_audit`), `src/kaleta/cli/tenant_admin.py` (reuse the service),
i18n `en.json` / `pl.json`, `docs/bdd.md`.

## Open questions

- More than one instance admin? Default: yes, an admin can promote an
  identity; the last admin cannot demote themselves.
- Hosted instance: is the panel on for the maintainer, or CLI only?
  Default: on — it shows exactly what the registry already holds.

## Implementation notes

- **Open questions — defaults taken.** (1) Several administrators: yes; an
  administrator can promote a login and demote one, and the last active
  administrator can be neither demoted nor disabled (the guard
  `LocalIdentityService` already had for disabling). (2) The panel is on for
  the hosted instance. Supabase has no `is_instance_admin`, so there the
  administrators are the e-mail addresses in `KALETA_INSTANCE_ADMINS`
  (comma-separated, read only with `KALETA_AUTH_BACKEND=supabase`): Supabase
  confirms an address before the account exists, and the list lives in the
  operator's deployment, not in a table someone could write to.
- **A family is created with its owner's login, and provisioned at once.**
  In the code a family exists only once a login has signed in for the first
  time (`TenantService.provision`). "Create family" creates the owner's local
  login (a one-time password, `must_change_password`) and provisions the
  family straight away, so it gets its name and shows up in the table before
  the owner's first sign-in. Until then its status shows as `pending` (owner
  never signed in). The owner sets the data passphrase at the first sign-in,
  just as after a sign-up, because the passphrase prompt depends only on
  whether the member already has key material. On `supabase` the panel does
  not create families: the identity lives in Supabase, and the hosted
  instance runs open sign-up.
- **Family name.** `tenants.name` has existed since ADR-35 and was never
  written. It now holds the label the administrator gives a family, as
  plaintext in the registry, visible to the operator just as e-mail addresses
  are (ADR-38 §5: "name, member count, status"). A family that signed itself
  up has no name; the table shows its owner's e-mail address instead.
- **Acceptance path.** The service tests are
  `tests/integration/test_instance_admin_service.py`, not `tests/unit/services/…`:
  they run on the registry database, and `scripts/spec_coverage.py` reads only
  `tests/integration` and `tests/e2e`, so the `KAL-ADM-*` scenarios they cover
  would otherwise not count as covered.
- **Part A.** `kaleta-admin`'s commands that change something (`suspend`,
  `resume`, `delete`, `create-login`, `reset-password`, `registration`) go
  through `InstanceAdminService`. `list` and `members` print the schema, which
  the panel never shows, so they keep their own queries. Each action writes
  one `admin_audit` row with `actor` = the administrator's auth subject, or
  `NULL` for `kaleta-admin`. `create-login` and `reset-password` now set
  `must_change_password`, and `logins` shows it (`must-change`); part B is
  what enforces it at sign-in. `reset-password --disable-mfa` on a family that
  is not active is now refused *before* the password changes. Before, it set
  the new password and only then refused to touch the second factor.
  `set_login_disabled` goes through the service too. The CLI's other output
  changes: `reset-password` of an unknown address says "No login 'x'." (the
  service's sentence).
- **Revocation reaches suspended families (review finding).** Nothing
  re-checks a login after sign-in: the session watermark and the token rows
  are what end a disabled member's access. Disabling a login, and resetting a
  password, now revoke in an *active or suspended* family. Before, a reset
  left a suspended family's sessions alone, so resuming the family brought
  them back. `users.sessions_valid_from` is in every schema's history, so a
  family suspended for a failed migration has it too. Only turning the
  second factor off still needs an active family. A reset revokes first and
  changes the password afterwards, so a failed revoke leaves the old password
  in place.
- **`create_family` undoes itself on failure (review finding).** Nobody sees
  the one-time password of a family whose provisioning failed. So the login
  and any part of the family that exists are removed, and the same address
  can be tried again.
- **Audit rows are their own commit**, after the action's (the services under
  it commit themselves). A crash between the two leaves an action without its
  row; the log line is written with the row. Accepted: the trail is for the
  administrators, not evidence against them. Any administrator can also reset
  another administrator's password and take the account; that is what being
  an administrator means here, and the row records who did it.
- **Part B — the page.** `/admin` (`views/admin.py`) gets everything through
  `kaleta.auth.admin.with_admin_service`, which runs `for_actor` on every call.
  For anyone else the page answers a plain 404. The navigation entry sits below
  the hairline, next to the API docs, and reads a session flag stamped at
  sign-in (`stamp_login_flags`, called from the session rotation route). A
  login promoted while signed in sees the entry after its next sign-in, and a
  demoted one keeps the entry until then, but the page refuses it.
- **Step-up.** The password, plus a TOTP or recovery code when the
  administrator has two-factor sign-in on, at most once per 15 minutes
  (`SESSION_ADMIN_STEP_UP_AT`). On a Supabase instance with a factor this is
  `HostedMfaService.prove`; without one it is a provider sign-in, signed out
  straight after. Failures count on `mfa_rate_limiter` under `admin:<user id>`.
- **Forced password change.** `stamp_login_flags` sets
  `SESSION_SET_BY_ADMIN` when the login's `must_change_password` is on.
  While it is set, the page guard sends every page to `/change-password`,
  ahead of `/unlock`, and the cookie API answers 401 (`api/deps.py`). The
  check is there because `/api/v1/` is past the page guard, and with
  encryption off nothing else would stop the session. The new password may not
  be the one that was given, and setting it signs the member's other browsers
  out. The flags are stamped at session rotation, and if stamping fails the
  session is signed out again (fail closed): a session that could not learn it
  must change its password is no session.
- **Review findings, part B.** Every action goes through the view's one `_act`,
  which is where the step-up is (disabling a login took its own path before).
  The audit line shows the registration mode in the page's language. Not
  done: a unit test of `prove_admin`'s lockout. The limiter is the same
  `mfa_rate_limiter` the code prompts use, and those prompts have such tests.
- **A latent leak found by the e2e (fixed here).**
  `TenantService._ensure_owner_user` and `_sync_email` opened the new
  family's session under `use_tenant` but flushed outside it. The audit row of
  the owner's `users` insert was then sealed under whatever context was
  current. For a family created from the panel, that was the administrator's
  own unlocked family, so the owner's passphrase setup failed to decrypt it.
  Until now, provisioning only ran from a locked sign-in. The whole block now
  runs under the new family's context, and a regression test makes the
  administrator's key current while creating a family.
- **Member limit.** `KALETA_HOUSEHOLD_MAX_MEMBERS` does not exist yet; it
  belongs to `hosted-household-sharing`. The panel shows the member count
  only, and the limit is added together with that plan.

## Implementation (filled by plan-archiver)
