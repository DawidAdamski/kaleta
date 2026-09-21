---
plan_id: hosted-household-sharing
title: Household sharing — two to four members on one account
area: auth / db / settings
effort: large
status: draft
roadmap_ref: ../roadmap.md#2027-directions
---

# Household sharing — two to four members on one account

## Intent

Parents run one set of finances together. One Kaleta account (one
tenant schema) must be usable by two to four people, each with their
own login, second factor and data passphrase, and the operator must
still be unable to read the data. An owner invites a partner; the
partner signs up, sets a passphrase, and asks to join; the owner
approves — after which both see and edit the same ledger, every change
records who made it, and removing a member revokes access for real by
re-keying the household. The same flow works for a self-hosted family
install with local logins.

Depends on [`hosted-tenancy-foundation`](hosted-tenancy-foundation.md)
(the `tenant_members` registry and the per-member `users` rows are laid
down there) and [`hosted-field-encryption`](hosted-field-encryption.md)
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
- Limits: `KALETA_HOUSEHOLD_MAX_MEMBERS` (default 4); exactly one
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
- `grep -c "KAL-HH-" docs/bdd.md | grep -qE '^[1-9]'` — new area
  `KAL-HH-*`: invite, join, approve, decline, remove/re-key, transfer
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

(filled in as work progresses)
