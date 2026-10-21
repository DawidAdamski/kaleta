---
plan_id: revocation-cache-wrong-tenant
title: Disabling a login forgets the wrong revocation-cache entry
area: auth
effort: small
status: in-progress
roadmap_ref: ../roadmap.md#auth
---

# Disabling a login forgets the wrong revocation-cache entry

## Intent
When the instance administrator disables a login from `/admin`, the process
must promptly forget the disabled member's cached revocation watermark so their
open browser sessions fail their next guard check at once (not after
`TTL_SECONDS` = 60 s). Today `forget_revoked_member` calls
`revocation_cache.forget(user_id)`, which keys the entry by the *current*
tenant — the administrator's own family — while the disabled member belongs to
*another* family. Every family's `users` table numbers from 1, so
`(admin_tenant, user_id)` and `(member_tenant, user_id)` are different keys for
different people. The administrator's own entry is dropped by mistake; the
disabled member's stale watermark survives for up to a minute, so their session
is not revoked promptly in this replica.

## Scope
Covers:
- `RevocationCache.forget` gains an explicit `tenant_id` keyword (default keeps
  the current-tenant behaviour the other two callers rely on).
- `forget_revoked_member` passes the disabled member's `revoked.tenant_id`.
- An integration test with two families reproducing the cross-tenant case.
- BDD scenario (`KAL-ADM-011`) + `spec_coverage` green.

Does **not** cover:
- The other two `revocation_cache.forget` callers
  (`session.keep_session_after_revocation`, `security_tab._sign_out_everywhere`)
  — both run in the acting user's own tenant context, so the current-tenant
  default is already correct for them. They are left untouched.
- The stale-write-guard chore, the household-name/MFA-column chore, or anything
  else in `chores.md`.

## Acceptance criteria
- `uv run pytest tests/integration/test_instance_admin_service.py -q`
- `grep -q "KAL-ADM-011" docs/bdd.md`
- `uv run python scripts/spec_coverage.py`
- `uv run mypy src/`
- `uv run lint-imports`

## Touchpoints
- `src/kaleta/auth/revocation_cache.py` — `_key`, `forget` signature.
- `src/kaleta/auth/local_logins.py` — `forget_revoked_member` call site.
- `tests/integration/test_instance_admin_service.py` — new test.
- `docs/bdd.md` — `KAL-ADM-011`.
- `docs/plans/chores.md` — tick the chore.

## Implementation notes
- The disabled member's tenant is already carried by
  `RevokedMember.tenant_id`, which `InstanceAdminService.set_disabled` builds
  from `membership.tenant.id` (the member's family). No new lookup is needed.
- `forget` is a pure in-memory `dict.pop`; passing an explicit tenant needs no
  session or tenant context, so it is safe to call after the `use_tenant` block
  in `set_disabled` has already reset the context back to the administrator's.
- `_key(user_id, tenant_id=None)` returns `(tenant_id, user_id)` when a tenant
  is given, else falls back to `current_tenant()` exactly as before —
  `valid_from` keeps calling `_key(user_id)` unchanged.
