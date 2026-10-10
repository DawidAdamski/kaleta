---
plan_id: instance-admin-panel
title: Instance admin panel — families, registration mode, password resets
area: auth / settings
effort: medium
status: draft
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

Depends on [`postgres-only`](postgres-only.md) (instance admin,
`local_identities`, `registration_mode`).

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

- `uv run pytest tests/unit/services/test_instance_admin_service.py -q`
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

## Implementation (filled by plan-archiver)
