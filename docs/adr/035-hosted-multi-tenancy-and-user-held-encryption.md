---
adr_id: "035"
title: "Hosted Multi-Tenancy: Schema per Account and Member-Held Field Encryption"
status: proposed
---

# ADR-35: Hosted Multi-Tenancy — Schema per Account and Member-Held Field Encryption

- **Context**: The hosted Kaleta (Supabase Postgres, see
  [deployment.md](../deployment.md)) today runs one demo user in one
  database. The commercial layer needs many accounts, and the operator
  wants to be unable to read what is in them: the only facts the operator
  should hold about an account are its members' **user ids and
  e-mails**. An account is a household: two to four people (parents,
  typically) share one ledger, each with their own login. Kaleta is
  server-rendered (NiceGUI) and every aggregate — day totals, budgets,
  net worth, forecasts — is a SQL query, so the server must be able to
  compute over the data while a user is signed in. The self-hosted
  Podman/SQLite path must keep working unchanged.
- **Decision**:
  1. **One Postgres schema per account.** Each account gets its own
     schema (`t_<12 hex>`) holding exactly today's single-user tables,
     including its own `users` row and `alembic_version`. A small
     `public.tenants` registry names the schema and a
     `public.tenant_members` table maps each auth subject to its tenant
     and role (`owner` or `member`, two to four per account). The
     app selects the schema per request with SQLAlchemy's
     `schema_translate_map` (compile-time rewriting), never with
     `SET search_path`, so Supabase's transaction pooler is safe. Inside
     a schema the app is exactly what it is on SQLite today, with one
     `users` row per member — services keep their signatures and the
     `user_id` columns from Q3 finally carry attribution (who added
     this) rather than access control.
  2. **Identity is delegated to Supabase Auth** on the hosted path
     (e-mail sign-up, verification, password reset, and — for
     [`auth-two-factor`](../plans/archive/auth-two-factor.md) — TOTP MFA).
     Self-hosted installs keep the argon2 `AuthService`. Both sit behind
     one `AuthProvider` interface selected by `KALETA_AUTH_BACKEND`.
  3. **Field-level encryption with keys only the members hold.** Each
     member chooses a *data passphrase* separate from the login
     password and gets an X25519 keypair: the private key is wrapped
     under a **key encryption key (KEK)** stretched from the passphrase
     with Argon2id (and a second time under a one-time **recovery
     code**); the public key is stored plain. One random 256-bit **data
     key (DEK)** per account is sealed to every active member's public
     key. Only wrapped private keys, public keys, sealed DEKs and KDF
     parameters are stored (in `public.tenant_members`). At login a
     member unlocks: passphrase → KEK → private key → DEK, which lives
     in process memory for the session and is never written to disk,
     to `app.storage.user`, or to logs. Inviting a member means the
     owner, while unlocked, seals the DEK to the newcomer's public key;
     removing one means the owner re-keys the household — new DEK,
     every row re-encrypted, sealed to the remaining members — because
     a removed member once held the old DEK in memory.
     Every column that carries user-written text — names, descriptions,
     notes, payees and their contact fields, account numbers, rule
     patterns, report configs, yearly-plan lines, audit-log snapshots —
     is stored as AES-256-GCM ciphertext through one SQLAlchemy
     `TypeDecorator`. Where the schema needs equality (unique payee, tag,
     institution and counterparty names; category name per parent;
     transfer detection by account-number suffix) a keyed **blind index**
     (HMAC-SHA256 under a key derived from the DEK) sits next to the
     ciphertext and carries the constraint.
  4. **Amounts, dates, currencies, enums and foreign keys stay in
     plaintext.** This is what keeps SQL aggregation, pagination and the
     Postgres CI matrix working. It is a deliberate, documented limit.
- **What the operator can and cannot see**: cannot read what any
  transaction was for, with whom, on which account, in which category,
  or any note, name, address or account number — not from the database
  console, not from a backup, not from a dump. Can see the shape of an
  account: how many accounts and transactions exist, their amounts,
  dates, types and currencies, budget figures, and the e-mail and user
  id. The privacy page must say this in those words.
- **Threat model**: the guarantee is *encrypted at rest under a key the
  operator does not have*. It is not end-to-end encryption: a
  server-rendered app decrypts on the server, so a compromised or
  malicious app host could capture a DEK while a user is signed in. The
  design defends against the realistic operator-side risks — database
  access, backups, exports, a leaked connection string, a Supabase
  breach — and says so honestly rather than claiming zero knowledge.
- **Rejected alternatives**:
  - *Encrypted SQLite file per account in Supabase Storage* (the whole
    database as one blob, decrypted into tmpfs for the session). Hides
    everything, including amounts, and needs no service changes — but
    allows one active session per account, makes durability depend on
    upload-after-write, and does not lead toward household sharing on
    the 2027 roadmap. Kept on record as the stronger-privacy option if
    the amounts-visible limit ever becomes unacceptable.
  - *Row-level tenancy in shared tables* (`user_id` filter everywhere).
    Requires touching every service query (only 4 of ~60 filter by
    `user_id` today) and one missed filter is a cross-tenant leak.
  - *Database per account.* Supabase provisions one database per
    project; many projects is neither affordable nor operable.
  - *Encrypting amounts too.* Every aggregate would move into Python;
    the whole reporting and forecasting layer would need rewriting.
  - *Deriving the KEK from the login password.* One password is nicer
    UX, but the login password is sent to Supabase Auth; the data
    passphrase must never leave the Kaleta process.
  - *Passphrase-wrapped DEK per member, no keypairs.* Simpler, and
    enough for one person — but the owner cannot re-wrap the DEK for a
    partner whose passphrase they do not know, so a household could
    never be re-keyed after a removal. The keypair costs one more
    `cryptography` primitive and buys real revocation.
  - *Sharing by e-mailing a secret.* An invite link that carries key
    material passes through the mail provider and the operator's SMTP;
    the invite here carries proof of e-mail only, and the key exchange
    is public-key sealing by an unlocked owner.
  - *`SET search_path` per connection.* Breaks under transaction
    pooling (port 6543); `schema_translate_map` does not.
- **Consequences**:
  - Substring search over encrypted text (`Transaction.description
    ILIKE`) is impossible in SQL; the transactions search path and rule
    matching move to in-process filtering. This is bounded by the size
    of a personal ledger and measured in the encryption plan.
  - A forgotten passphrase without the recovery code means that
    member's private key is unrecoverable. In a household the data
    survives (it is sealed to the others; the member re-keys and is
    re-approved); for a single-member account the data is gone, and
    sign-up must say so and force the user to save the recovery code.
  - `public.tenants` and `public.tenant_members` (plus
    `tenant_invites`) are the only cross-tenant tables, and they hold
    no financial data: tenant id, schema name, status and key version;
    per member the auth subject, e-mail, role, public key, wrapped
    private key, sealed DEK and KDF parameters. What one member can
    learn about another through the app is e-mail, display name and
    key fingerprint.
  - Migrations run per schema; provisioning an account is
    `CREATE SCHEMA` + `alembic upgrade head` for that schema.
  - Self-hosted installs run `KALETA_TENANCY=single` and
    `KALETA_ENCRYPTION=off` by default and change nothing. Encryption
    can be switched on for a single-tenant install; the same code path
    then protects a self-hoster's SQLite file.
- **Plans**: [`hosted-tenancy-foundation`](../plans/hosted-tenancy-foundation.md),
  [`hosted-field-encryption`](../plans/hosted-field-encryption.md),
  [`hosted-household-sharing`](../plans/hosted-household-sharing.md),
  [`hosted-supabase-rollout`](../plans/hosted-supabase-rollout.md).
