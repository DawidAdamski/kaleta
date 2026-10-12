---
plan_id: hosted-household-sharing
title: Household sharing — up to ten members on one family account
area: auth / db / settings
effort: large
status: in-progress
roadmap_ref: ../roadmap.md#2027-directions
---

# Household sharing — up to ten members on one family account

## Intent

Parents run one set of finances together. One Kaleta account (one
tenant schema) must be usable by up to ten people, each with their
own login, second factor and data passphrase, and the operator must
still be unable to read the data. An owner invites a partner; the
partner signs up, sets a passphrase, and asks to join; the owner
approves — after which both see and edit the same ledger, every change
records who made it, and removing a member revokes access for real by
re-keying the household. The same flow works on a self-hosted instance
with local logins (ADR-38: one layout everywhere).

Depends on [`postgres-only`](archive/postgres-only.md) (local logins on the
multi layout, ADR-38), [`hosted-tenancy-foundation`](archive/hosted-tenancy-foundation.md)
(the `tenant_members` registry and the per-member `users` rows are laid
down there) and [`hosted-field-encryption`](archive/hosted-field-encryption.md)
(the per-member keypair hierarchy is defined there so a single-member
account and a household use one code path).

## Scope

### 1. Membership model

- `public.tenant_members` (from the foundation plan) is the source of
  truth: `tenant_id`, `auth_subject`, `email`, `role`
  (`owner|member`), `status` (`pending|active|removed`), `joined_at`,
  `removed_at`, `user_id` (the member's row in the tenant-schema
  `users` table), plus the key columns from the encryption plan
  (`public_key`, `private_key_wrapped`, `private_key_salt`,
  `kdf_params`, `recovery_wrapped`, `dek_sealed`).
- Limits: `KALETA_HOUSEHOLD_MAX_MEMBERS` (default 10, ADR-38); exactly one
  `owner`; the owner can hand ownership to another active member
  ("Make owner", needs a fresh MFA code when MFA is on).
- Roles are deliberately two: `owner` (invite, approve, remove,
  transfer ownership, delete the account) and `member` (everything
  else — full read/write of the finances). A read-only `viewer` is a
  follow-up; it needs nothing in the key design.
- Tenant-schema `users` gets one row per member (`username` =
  display name chosen at join, `email`), so the existing `user_id`
  columns finally carry attribution.

### 2. Invite → join → approve

- **Invite** (owner, Settings → Household): e-mail + role. Creates a
  `tenant_invites` row (`token_hash`, `email`, `role`, `expires_at`
  72 h, `accepted_at`) and sends a link
  `KALETA_PUBLIC_URL/join?token=…` (hosted: through the same SMTP as
  Supabase Auth mails; local: the link is shown to the owner to pass on
  — self-hosters rarely have SMTP). The link carries **no key
  material**; it only proves the e-mail was invited.
- **Join** (invitee): the link lands on sign-up or login for that
  e-mail (hosted: Supabase Auth; local: the owner pre-creates the login
  with a one-time password, or the invitee sets one from the link).
  The invitee then sets their data passphrase and recovery code, which
  generates their keypair (encryption plan §1), and their membership
  becomes `pending`. They see "Waiting for <owner> to approve" and
  nothing else.
- **Approve** (owner, must be unlocked): Settings → Household lists
  pending members with e-mail and public-key fingerprint (8 groups of
  4 hex, shown so a careful household can compare it over the phone).
  Approve = seal the DEK to the member's public key, insert their
  `users` row, set `active`; the member's next page load unlocks
  normally. Decline = delete the pending row.
- **Rejoin after recovery**: a member who lost passphrase and recovery
  code cannot unwrap their private key; "Reset my keys" generates a
  new keypair and drops them to `pending` for a fresh approval. Their
  data is safe — it is the household's, sealed to the others.

### 3. Remove a member — real revocation

- Removing an active member (owner, unlocked): mark `removed`, kill
  their sessions (`KeyRing.lock` by member and a session-version bump
  checked by the route guard), and **re-key the household in the same
  transaction**: generate a new DEK, re-encrypt every `EncryptedText`
  column and recompute every blind index in the tenant schema, seal
  the new DEK to every remaining member's public key, and bump
  `tenants.key_version`. Rows carry the key version in the ciphertext
  header (encryption plan, version byte becomes a two-byte
  `version|key_version`) so a half-finished re-key is detectable and
  resumable; the operation runs with the tenant marked `rekeying`, all
  other sessions get a "household is being re-keyed, try again in a
  moment" page, and the job is idempotent.
- Budget: a ledger of 50 000 transactions re-keys under 60 s on the CI
  Postgres; the measurement goes into implementation notes. Above a
  threshold the UI warns before starting.
- Leaving voluntarily (`member`) is the same operation, triggered by
  the member; the owner is notified.
- A removed member's e-mail may be invited again; they start over as
  `pending` with a new keypair.

### 4. Working together

- Attribution: `AuditLog` gains `user_id`; the History tab shows who
  changed what; transaction, planned-transaction and import-run rows
  record `user_id` on create (they already have the column). The
  transactions table gets an optional "Added by" column and filter.
- Concurrency: last write wins at row level as today. Two members
  editing the same dialog is rare in a household and is not
  arbitrated; a stale-write guard on `updated_at` (`ConflictError`
  "this was changed by <name> a moment ago — reload?") covers the
  case cheaply. No live push between sessions in this plan.
- Per-member preferences stay per member (`app.storage.user`:
  theme, language, dashboard layout, `events_enabled`); shared data
  stays in the schema. The wizard's "mentor" and monthly-readiness
  state are shared (they describe the household), which the wizard
  copy should reflect ("your household").
- Notifications from `wizard-reminders`, when it lands, go to every
  active member.

### 5. Settings → Household (new tab)

- Members list (name, e-mail, role, joined, MFA on/off as reported by
  the provider, fingerprint), Invite, pending approvals, Remove,
  Transfer ownership, Leave household, and the household name (the
  only new text column, `EncryptedText`). i18n `household.*`.
- Deleting the account (rollout plan) requires `owner` and lists the
  members who will lose access.

### 6. Self-hosted (`single` tenancy, `local` auth)

- Same feature: the owner creates logins from Settings → Household
  (username + one-time password); the join and approve steps are the
  same pages. With `KALETA_ENCRYPTION=off` the keypair steps are
  skipped and approval is one click. The existing first-run "create
  your account" user becomes the `owner`.

### Not in scope

- A `viewer` role, per-account or per-category permissions.
- Several households per identity (one login belongs to one tenant;
  switching households is a later plan).
- Live multi-user sync (websocket refresh of another member's change).
- Notifying members by e-mail about each other's changes.

## Acceptance criteria

- `uv run pytest tests/unit/services/test_household_service.py -q` —
  invite expiry and single use, approve seals to the right key,
  member limit, exactly-one-owner invariant, transfer ownership
- `uv run pytest tests/unit/crypto/test_rekey.py -q` — re-key rewrites
  every encrypted column and blind index, old DEK cannot read new rows,
  header carries the new key version, interrupted re-key resumes
- `uv run pytest tests/integration/test_household_rekey_budget.py -q`
  — 50 000-row re-key under the recorded budget (Postgres job)
- `uv run pytest tests/integration/test_household_isolation.py -q` —
  a removed member's session is rejected on the next request; a
  pending member sees no data; both active members read and write the
  same rows
- `uv run pytest tests/e2e/test_household.py -q` — owner invites,
  second browser context signs up and sets a passphrase, owner
  approves, both see the same transaction, owner removes, second
  context is locked out
- `uv run python scripts/spec_coverage.py`
- `grep -c "KAL-HHS-" docs/bdd.md | grep -qE '^[1-9]'` — new area
  `KAL-HHS-*`: invite, join, approve, decline, remove/re-key, transfer
  ownership, attribution in history
- `./scripts/verify.sh --e2e`
- `[manual]` Two phones, two authenticator apps, one household on the
  hosted instance: both unlock, one adds a transaction, the other sees
  it after refresh; remove one, confirm the lock-out and that the
  remaining member still unlocks.

## Touchpoints

`src/kaleta/models/tenant.py` (`key_version`, `status=rekeying`),
`src/kaleta/models/tenant_member.py`, `src/kaleta/models/tenant_invite.py`
(new), `src/kaleta/models/user.py` (`email`, `display_name`),
`src/kaleta/models/audit_log.py` (`user_id`), `src/kaleta/db/audit.py`,
`src/kaleta/db/types.py` (key-version header), `src/kaleta/crypto/{keys,keyring,rekey}.py`,
`src/kaleta/services/{household,key,tenant,audit,transaction}_service.py`,
`src/kaleta/auth/session.py` (session version), `src/kaleta/auth/middleware.py`,
`src/kaleta/auth/providers/{local,supabase}.py` (invite mail, one-time
password), `src/kaleta/views/join.py` (new), `src/kaleta/views/settings/household_tab.py`
(new), `src/kaleta/views/settings/history_tab.py`, `src/kaleta/views/transactions/page.py`
("Added by"), `src/kaleta/views/wizard*.py` (copy), `alembic/versions/<new>_household.py`,
`alembic_public/versions/<new>_members_invites.py`, `src/kaleta/i18n/{en,pl}.json`,
`docs/bdd.md`, `docs/privacy.md` (what a member can see about another:
e-mail, display name, fingerprint), `docs/tech-stack.md`.

## Open questions

- Should approval require the owner to re-enter the passphrase even
  when unlocked (a deliberate "I am sealing our data to this key"
  moment), or is an MFA step-up enough? Recommendation: step-up when
  MFA is on, passphrase otherwise.
- Re-key on removal is the honest choice but heavy; is "remove without
  re-key, warn the owner" acceptable as a faster option for a member
  who simply lost a phone (their key is still wrapped, no exposure)?
  Recommendation: offer both, default to re-key, explain the
  difference in one sentence.
- Display name: chosen at join, editable by the member only, or also
  by the owner? Member only.
- Should the invite e-mail come from Kaleta's SMTP or be a Supabase
  Auth "invite user" call (`/auth/v1/invite`, admin-only)? The admin
  call creates the identity up front and skips the sign-up form; the
  trade-off is that the service-role key then lives in the app for
  one more purpose. Decide with the rollout plan's SMTP choice.

## Implementation notes

### Delivery in three PRs

The plan spans every layer, so it lands as three branches, each green on its own:

- **Part A — the household core** (`feat/household-sharing-part-a`): `HouseholdService`
  (invite, join, approve, decline, remove, leave, transfer ownership, reset keys), the
  re-key, sign-in of pending members, revocation of a removed one, the member limit.
  Service-level `KAL-HHS-*` scenarios, unit and integration tests, the re-key budget.
- **Part B — the pages**: Settings → Household, `/join`, the waiting and "being re-keyed"
  screens, the fingerprint, the e2e test, `docs/privacy.md`.
- **Part C — working together**: `audit_log.user_id` and "who" in History, "Added by" on
  transactions, the stale-write guard, the wizard's household copy.

### What was already in place

The encryption and tenancy plans laid most of the ground: the `tenant_members` key
columns, `tenant_invites`, `TenantStatus.REKEYING`, `tenants.key_version`, the
`awaiting_key` key status (a member with a keypair and no sealed key), `users.email` /
`display_name`, the session watermark (`users.sessions_valid_from`) and the key ring's
`lock_member`. Part A builds on these and adds no migration.

### Decisions (Part A)

- **One invite flow on both layouts: a link.** Kaleta has no SMTP of its own, so the
  owner is shown the link to pass on, hosted included; sending it by e-mail waits for the
  rollout plan's SMTP choice (open question 4). On a `local` instance the invitee sets
  their password on the link's page, which creates the login; the "owner pre-creates a
  login with a one-time password" variant of §6 is not built — one path, not two.
- **The token proves the invitation; an e-mail match does so only where the provider
  verified the address.** A Supabase identity signing in for the first time with no
  membership joins the household that invited its (verified) e-mail instead of getting a
  family of its own. A `local` identity never joins by e-mail match — a local address is
  whatever was typed — only through the token.
- **A member joins as `pending` with a `users` row.** The plan put the `users` row at
  approval, but a pending member must sign in to set their passphrase (that is what makes
  the keypair to approve), and a session is opened as a `users` row. The row carries
  nothing but the e-mail and display name.
- **Only an active member creates a data key.** A pending member whose household has no
  key yet (the owner never unlocked) gets a keypair only — otherwise the newcomer's
  set-up would generate the household's key and encrypt the ledger under it.
- **Pending without encryption.** With `KALETA_ENCRYPTION=off` (debug only) there is no
  keypair to wait for: a pending member's sign-in is refused until approved, and approval
  is one step.
- **Re-key in one transaction, then a sweep.** The rows are rewritten (read under the old
  key, written under the new, blind indexes recomputed), the new key sealed to every
  remaining member, the removed member marked and `key_version` bumped — all in one
  transaction on the family's session, which reaches `public` too. A crash rolls it all
  back; nothing is half re-keyed, so "resumable" is "run it again". Before it starts, the
  key ring *freezes* the family (every unlock of it reads as locked, a new unlock is
  refused, the tenant is marked `rekeying`); after the commit the ring's entries of the
  remaining members get the new key, and a sweep rewrites any row still carrying the old
  version (a write that bound its parameters before the freeze and committed after the
  pass) while the old key is still in memory. Then the family thaws.
- **The key version stays one byte.** The header already carries it (`\x01 | version`);
  the plan's two-byte header is not needed. After 255 it wraps to 1 — only old and new
  must differ.
- **A tenant left `rekeying`** by a crash is put back to `active` at start-up: the
  transaction rolled back, so its rows and keys are the old ones.
- **Remove without re-key** is offered (open question 2): the member is removed and their
  sealed key deleted, the ledger keeps its key. Default is re-key.
- **Decline deletes the pending member** and, for a `local` login the invite created,
  the login too — otherwise its next sign-in would provision a family of its own. "Created
  by the invite" is "created after the invitation was issued" (`accept_with_password` is
  the only way a login with that address appears then); an older login, or the
  administrator's, is never deleted. A *returning* member (one with `removed_at`) who is
  declined goes back to `removed` instead, row and login kept.
- **A removed member's row stays** (`removed`, `removed_at`) so the household's history
  keeps the name; a sign-in is refused, and a new invitation for the address reuses the
  row as `pending` with no keys.
- **The owner cannot leave or reset keys** — ownership goes to another active member
  first. The household always has exactly one owner.
- **Fingerprint**: the first 16 bytes of SHA-256 of the public key, as 8 groups of 4 hex.
- **Re-key budget, measured**: 50 000 transactions (descriptions, a third with notes)
  re-key in 1.2 s on the test PostgreSQL 18 (macOS, Podman), against the 60 s budget
  (`tests/integration/test_household_rekey_budget.py`, slow tier). The pass is
  `executemany` in batches of 1 000; AES-GCM per value is microseconds, so the database
  round trips dominate.
- **Tests' location**: `spec_coverage` reads `tests/integration` and `tests/e2e` only, so
  the `KAL-HHS-*` scenarios are covered by `tests/integration/test_household_isolation.py`;
  the plan's unit files hold the refusals and edges (`test_household_service.py`) and the
  re-key's mechanics (`tests/unit/crypto/test_rekey.py`: interrupted pass, late writes,
  freeze). Each safeguard was checked by breaking it: no sweep, no old-key reader and a
  pending member allowed to create the key each fail a test.
- **`KAL-HHS-*`, not `KAL-HH-*`**: scenario areas are three or four letters
  (`scripts/spec_coverage.py`, `KAL-[A-Z]{3,4}-NNN`); the acceptance criterion is updated
  to match rather than the checker widened.

### After review (Part A)

- **A removed member's API tokens are revoked** in the same transaction as the removal
  (both with and without re-key): with encryption on they were already inert (no unlock
  to ride on), but not with it off, and a re-approved member would have got them back.
- **Approval checks the key and the keypair**: the owner's key must be the household's
  current version, the household not mid re-key, and `expected_fingerprint` (what the page
  showed) must still match — a keypair replaced between showing and the click is refused.
- **One re-key at a time**: the tenant row is claimed `FOR UPDATE` from `active` to
  `rekeying` before the freeze; a second run is refused without freezing or thawing.
- **The sweep looks twice** and logs an error if the second look still finds rows under the
  old version. **Known residual**: a transaction that wrote under the old key before the
  freeze and stays open past the last look commits rows no key opens (the old key is gone
  after the thaw). The freeze confines that to a write in flight across the whole re-key
  (≈1 s for 50 000 rows); closing it fully needs a lock every writer takes, which is not
  worth a lock on every write.
- **`release_interrupted_rekeys` runs at every start.** With one process (the key ring is
  per-process by design, ADR-35) that is only after a crash. A second replica starting
  during a live re-key would reset its mark and let sign-ins in mid-pass; multi-replica
  deployments are not supported by the key ring anyway, and this is one more reason.
- **Spending an invitation locks its row**, and two tabs accepting one link at once get a
  `ConflictError`, not a raw `IntegrityError`.
- **Re-inviting at the limit** counts the replaced link as freed, and the limit is checked
  before the old link is deleted.

### Decisions (Part B — the pages)

- **Settings → Household** is a tab for everyone in a household: the members (name,
  e-mail, role, status, joined, fingerprint), the member's own display name and "Leave",
  and for the owner the invitation form, the open invitations, and per member Approve,
  Decline, Remove, Make owner. The view reaches the service through
  `kaleta.auth.household`, which also drops what this process holds for a member who lost
  access (`forget_revoked_member`: the cached revocation watermark, their key-ring
  entries) — the service cannot import the auth layer.
- **Approving asks for the data passphrase again** (open question 1), always, rather
  than an MFA step-up when MFA is on: it is the deliberate "I am sealing our data to
  this key" moment, the passphrase is what proves the owner holds the key being sealed,
  and one path is simpler than two. The dialog shows the fingerprint and passes it as
  `expected_fingerprint`.
- **Making someone else the owner asks for a fresh MFA code** when MFA is on — the
  Security tab's step-up, now shared rather than copied.
- **Remove** opens one dialog: a "re-key the household" switch, on by default, and one
  sentence on the difference (open question 2).
- **`/join?token=…`** is public. With `local` logins it shows the invited address and
  asks for a password (the login is created for that address only), then signs the
  invitee in and sends them to `/unlock` to set their passphrase. With Supabase Auth it
  points to sign-up and sign-in with that address — the first verified sign-in joins (Part
  A). A used, replaced or expired link says so, without telling whether the address has an
  account.
- **`/unlock` gains two faces.** *Waiting*: "Waiting for <owner's e-mail> to approve",
  with the member's own fingerprint to read out over the phone, "Check again" and "Sign
  out". *Being re-keyed*: shown while the key ring holds the household frozen, with "Try
  again". The owner's e-mail rather than a display name: the pending member's session
  reads only the registry.
- **"Reset my keys"** sits on `/unlock` behind the recovery-code form ("Lost the code
  too?"), for members other than the owner — it is for someone who cannot unlock, so it
  cannot live in Settings.
- **Not built in Part B**: the household name (a new `EncryptedText` column and a
  migration, with nothing yet reading it) and the per-member "MFA on/off" column (a
  provider call per member on every render of the tab). Both are in `chores.md`.
- **The e2e shares a payee, not a transaction**: one dialog instead of an account plus a
  transaction, and the same proof — a row written under the household's key by one member
  is read by the other.
- **Tests (Part B)**: `tests/e2e/test_household.py` (`KAL-HHS-013`, `-014`) runs the plan's
  e2e criterion on an app of its own (port 8089, `local` logins, encryption on), two
  browser contexts. The *being re-keyed* face of `/unlock` has no e2e: the re-key of an
  e2e-sized ledger lasts milliseconds, too short to land a page load inside it. It is the
  key ring's `is_frozen` (covered in `tests/unit/crypto/test_rekey.py`) drawn as a page.

### After review (Part B)

- **A spent link is a login, not an error, on `/join`**: once the invitation has created
  the login, a failure of the sign-in that follows says the login is ready and to sign in
  on `/login` — the link no longer works, so "try again" there would be a dead end.
- **The revocation contract of `kaleta.auth.household`** (removal and leaving forget the
  member in this process) is pinned by `tests/unit/auth/test_household_auth.py`.
- **The invitation link's base** is `KALETA_PUBLIC_URL` when set, otherwise the request's
  own base URL — behind a proxy that rewrites `Host`, set `KALETA_PUBLIC_URL`.

### Decisions (Part C — working together)

- **Rows already record who added them**: `kaleta.services.attribution` stamps `user_id` on
  every new `UserOwnedMixin` row from `TenantContext.member_user_id` (laid down by the
  tenancy plan), transactions, planned transactions and import runs included. Part C adds
  nothing there.
- **`audit_log.user_id`** is a new nullable column (tenant-schema migration, `ON DELETE SET
  NULL`, no backfill: older entries say "—"), stamped from the same context by the flush
  listener and by the auth and token events. A plain integer next to the encrypted
  snapshots: which member changed something is no more than `transactions.user_id` already
  shows the operator.
- **A member's name** is their `users.display_name`, else the part of their e-mail before
  the `@` — one rule, `MemberNameService.name`, which the Household tab now uses too, so a
  member is called the same everywhere. A removed
  member keeps their row (Part A), so their past entries keep their name.
- **"Who" and "Added by" appear only in a household** — once the family has two or more
  `users` rows. Alone, every row is the user's own: the History column and the ledger's
  column and filter would say one name over and over, and the ledger (artboard `2a`) stays
  as drawn for everyone who is not sharing.
- **The stale-write guard covers the transaction dialog**, the one place two members
  realistically edit the same row (categorising the month). `TransactionUpdate` takes an
  optional `expected_updated_at`; when the row moved on since the dialog loaded it,
  `update` raises `StaleWriteError` (a `ConflictError`, 409 on the API) naming the member
  of the row's last audited change, and the dialog says "changed by <name> a moment ago"
  with a Reload that loads their version. Without the field (every older API client)
  last write wins, as before. Other editors are not guarded; `chores.md` has the line.
- **The wizard's copy**: a household of two or more sees one sentence under the wizard's
  and Monthly Readiness's subtitles — the progress there is shared, what one marks done
  the others see. Alone, the copy is unchanged.
- **Tests (Part C)**: `tests/integration/test_household_working_together.py` (`KAL-HHS-015`,
  `-016`, `-017`) — the history's member, the "Added by" filter, a stale save refused with
  the other member's name and the row keeping their change; each safeguard was checked by
  breaking it (no stamp on audit rows, no guard, no filter: each fails a test). The e2e
  (`tests/e2e/test_household.py`) adds what the owner's pages show once the partner is in:
  "ania" and "jan" in History, the "Added by" chip (absent before the invitation) and the
  wizard's sentence (`KAL-HHS-018`). The stale-write banner has no e2e of its own: two
  browser contexts editing one transaction would need an account, a category and a
  transaction built through the UI first, for a banner whose text and trigger the
  integration test already pins.

### After review (Part C)

- **A version without a time zone is UTC**: `expected_updated_at` from an API client that
  leaves the zone out would otherwise never equal the stored `timestamptz`, and every save
  would read as stale.
- **A member's own save in another tab** is refused the same way, but reads "changed
  elsewhere", not "changed by" themselves.
- **The audit row's foreign key** carries PostgreSQL's default name
  (`audit_log_user_id_fkey`), the one a schema built from the models gets.
- **Known edge, not reachable today**: a flush that deleted the acting member's own `users`
  row would write audit rows pointing at it. Removed members keep their row (Part A), and a
  declined member's row is deleted by the owner, not by themselves.
