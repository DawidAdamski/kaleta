---
plan_id: hosted-field-encryption
title: Hosted — user-held data passphrase and field-level encryption
area: db / auth / settings
effort: large
status: archived
archived_at: 2026-10-03
roadmap_ref: ../../roadmap.md#2027-directions
---

# Hosted — user-held data passphrase and field-level encryption

## Intent

The operator of the hosted Kaleta must not be able to read what an
account contains — not from the Supabase console, not from a backup,
not from a dump. At sign-up each member chooses a data passphrase; from it
a key is derived that unwraps that member's private key, which in turn
opens the account's data key — held only in memory while the member is
signed in. Every column carrying user-written text is stored as
ciphertext; equality the schema depends on is served by keyed blind
indexes. Amounts, dates, currencies and enums stay readable so SQL
aggregation keeps working ([ADR-35](../../adr/035-hosted-multi-tenancy-and-user-held-encryption.md)
lists what the operator can still see). The same machinery, switched on,
protects a self-hoster's SQLite file.

Depends on [`hosted-tenancy-foundation`](hosted-tenancy-foundation.md)
for `TenantContext`, `public.tenant_members` and the key-material
columns. The keypair-per-member design is what lets
[`hosted-household-sharing`](../hosted-household-sharing.md) add and remove
members later without changing this plan.

## Scope

### 1. Key hierarchy (`kaleta/crypto/`)

- Three layers, all in `cryptography`, which becomes a base dependency
  (the only new one):
  1. **Member keypair** — X25519. `generate_member_keys()`; the private
     key is wrapped with AES-256-GCM under a KEK from
     `derive_kek(passphrase, salt, params)` (**Argon2id** via
     `argon2-cffi`'s `low_level.hash_secret_raw`; parameters stored per
     member so they can be raised later, start at `t=3, m=64 MiB,
     p=1`). Public key stored plain in `tenant_members.public_key`.
  2. **Data key (DEK)** — `generate_dek()` (32 random bytes) per
     account, sealed to each active member's public key
     (`seal(dek, public_key)` / `open(sealed, private_key)`: X25519
     ECDH with an ephemeral key + HKDF-SHA256 + AES-256-GCM, i.e. a
     sealed box). Stored per member in `tenant_members.dek_sealed`.
  3. **Blind-index key** — `derive_index_key(dek)` = HKDF-SHA256 of the
     DEK with info `"kaleta-blind-index"`; never stored.
  A single-member account runs the same three layers; the extra cost
  over a plain passphrase-wrapped DEK is one sealed box per unlock.
- `recovery.py`: at sign-up generate a 26-character Crockford-base32
  recovery code, derive a second KEK from it (same Argon2id), wrap the
  **private key** again. Show the code once, force a checkbox "I saved
  it", offer download as a text file. Recovery = unwrap with the code,
  choose a new passphrase, re-wrap. No recovery code and no passphrase
  means that member's key is gone: for a household the member resets
  keys and is re-approved (sharing plan §2); for a single-member
  account the data is gone, and the sign-up copy says so.
- `keyring.py`: process-local `KeyRing` — `dict[session_key, (DEK,
  private_key)]` with TTL equal to `session_ttl_hours`,
  `unlock(member, passphrase)` (passphrase → KEK → private key → DEK),
  `lock(session)`, `lock_member(member_id)` (used on removal),
  `get() -> DEK` from the current `TenantContext`. The private key
  stays in the ring only because the owner needs it to seal the DEK for
  a newcomer and to re-key; a `member` could drop it after unlock.
  Never touches `app.storage.user`, never logs key bytes; `__repr__`
  redacts. On process restart every session is locked and must unlock
  again (documented, accepted).
- Passphrase change: unwrap the private key with the old KEK, wrap
  with the new, update the row; the recovery wrap and the sealed DEK
  are untouched. Rotating the DEK itself (re-encrypting every row) is
  built in [`hosted-household-sharing`](../hosted-household-sharing.md)
  §3; this plan leaves the ciphertext header room for it (a key-version
  byte after the format byte).

### 2. Column type (`kaleta/db/types.py`)

- `EncryptedText(TypeDecorator)` over `LargeBinary` (Postgres `bytea`,
  SQLite `BLOB`): `process_bind_param` encrypts with AES-256-GCM,
  12-byte random nonce, AAD = table and column name, two-byte header
  (`format` `\x01`, `key_version` from `tenants.key_version`) so the
  format can change and a re-key can tell old rows from new;
  `process_result_value` decrypts. With `KALETA_ENCRYPTION=off` (the
  default in `single` mode) the type stores UTF-8 plaintext under
  format byte `\x00`, so a self-hoster can switch encryption on later
  and the reader accepts both.
- `BlindIndex` helper: `blind_index(value) -> str` = hex HMAC-SHA256
  under the index key of the normalised value (NFKC, casefold, collapsed
  whitespace); `None` when encryption is off and the plain column carries
  the constraint. Columns named `<col>_bidx`, `String(64)`, indexed.
- `mypy --strict` typing: `EncryptedText` is `TypeDecorator[str]`; the
  models keep `Mapped[str]` / `Mapped[str | None]` so services do not
  change.

### 3. Columns that move to `EncryptedText`

| Model | Columns | Blind index |
|---|---|---|
| `Account` | `name`, `external_account_number` | `external_account_number_bidx` on the normalised digits; a second `external_account_number_sfx_bidx` on the last 8 digits for [ADR-20](../../adr/020-transfer-detection-via-counterparty-account-number-matching.md) suffix matching |
| `Transaction` | `description`, `notes` | — |
| `TransactionSplit` | `note` | — |
| `Payee` | `name`, `website`, `address`, `city`, `country`, `email`, `phone`, `notes` | `name_bidx` (unique) |
| `Category` | `name` | `name_bidx`; unique constraint becomes `(parent_id, type, name_bidx)` |
| `Tag` | `name`, `description` | `name_bidx` (unique) |
| `Institution` | `name`, `website`, `description` | `name_bidx` (unique) |
| `Asset` | `name`, `description` | — |
| `PlannedTransaction` | `name`, `description` | — |
| `ReserveFund` | `name` | — |
| `Subscription` | `name`, `url`, `notes` | — |
| `PersonalLoan` counterparty / loan / repayment | `name`, `notes`, `note` | `name_bidx` (unique) on counterparty |
| `SavedReport` | `name`, `config` | — |
| `CategorisationRule` | `pattern` | — |
| `ImportRule` | `filename_pattern` | — |
| `ImportRun` | `filename` | — |
| `YearlyPlan` | `income_lines`, `fixed_lines`, `variable_lines`, `reserves_lines` | — |
| `AuditLog` | `old_data`, `new_data` | — (the JSON snapshot is serialised from mapped attributes, i.e. plaintext, so the whole blob is encrypted) |
| `DismissedCandidate` | `merchant_key` | equality only → store as blind index instead of ciphertext |

Not encrypted, on purpose: amounts, dates, `currency`, enums, colours,
icons, `logo_path`, `user_id`/FKs, `MonthlyReadiness.seen_planned_ids`
(ids only), `CurrencyRate` (public NBP data), `AppEvent` (already has
no user text by design), `ApiToken.label` (operator-visible on purpose
— it is what support sees).

### 4. Queries that cannot run on ciphertext

- `TransactionService.list` search (`description ILIKE %s%`): fetch the
  filtered page *without* the text predicate, then apply the search in
  Python over the tenant's rows for the selected period, with a hard cap
  and a measured budget (acceptance: 50 000 transactions searched under
  300 ms on the CI Postgres). Sorting and pagination stay in SQL; the
  text filter becomes the last step and the count is computed from the
  filtered list. Record the measurement in implementation notes.
- `RuleService` matching (`lower(payee.name) LIKE`, `lower(description)
  LIKE`): rules already run per imported row; match in Python against
  the decrypted payee name and description.
- `AccountService` transfer detection (`external_account_number ILIKE
  %digits`): compare `external_account_number_sfx_bidx`.
- `DedupeService` `ilike` uses: same treatment; `merchant_key` becomes a
  blind index.
- Uniqueness errors: `ConflictError` messages keep working because the
  `IntegrityError` comes from the `_bidx` unique index — map the new
  constraint names in the existing handlers.

### 5. Unlock flow and UI

- Sign-up (hosted): step 2 after e-mail verification — choose data
  passphrase (min 12 chars, zxcvbn-style meter is out of scope; length +
  "not equal to login password" check), confirm, show recovery code,
  require acknowledgement. This generates the keypair; for a new
  account provisioning (foundation plan) also generates the DEK and
  seals it to that key, writing everything into
  `public.tenant_members`. For an invited member the DEK is sealed
  later, by the owner (sharing plan §2).
- Login (hosted): after `AuthProvider.sign_in` (and MFA when
  `auth-two-factor` lands) the user lands on `/unlock`: passphrase field,
  "use recovery code" link. Route guard: every data page requires an
  unlocked keyring; `/unlock`, `/login`, `/settings/security` (for
  passphrase recovery) and static assets are exempt. API bearer requests
  on a locked tenant get `423 Locked` with `{"error": {"code":
  "tenant_locked"}}` — bearer tokens cannot unlock; a session must be
  open (documented limitation; a token-scoped unlock is a follow-up).
- Settings → Security: "Change data passphrase", "Show recovery status"
  (whether a recovery wrap exists), "Regenerate recovery code" (needs the
  passphrase), "Lock now".
- Settings → Privacy: a plain-language box stating what is encrypted and
  what the operator can still see, copied from ADR-35.
- Self-hosted (`single` mode): `KALETA_ENCRYPTION=passphrase` enables
  the same flow with the key material stored in a new `local_key_material`
  table (one row per local user, same columns as `tenant_members`'
  key block). Default stays `off`. Turning encryption on for an
  existing SQLite database runs a one-off `scripts/encrypt_database.py`
  (reads plaintext rows, writes ciphertext, takes a backup first via the
  existing `BackupService`).

### 6. Seed, demo, backups, export

- `scripts/seed.py` and `scripts/reset_demo.py` run through the ORM, so
  they encrypt transparently; the demo tenant gets a fixed passphrase
  documented next to the demo credentials.
- Data export (Settings → Data) produces plaintext from the unlocked
  session as today. Backup restore of a full-schema file into an
  encrypted tenant re-encrypts on insert (ORM path).
- Alembic migration for the columns: add `_bidx` columns, change text
  columns to `LargeBinary`, backfill by re-writing every row through the
  `TypeDecorator` under version byte `\x00` (plaintext) so existing
  single-mode databases upgrade without a key; `render_as_batch` for
  SQLite.

### Not in scope

- End-to-end (client-side) encryption; encrypting amounts and dates.
- DEK rotation / re-encryption of a tenant → sharing plan §3 (this
  plan only reserves the key-version header byte).
- Substring search index (n-gram blind index) — only if the in-process
  filter misses its budget.
- Token-scoped unlock for headless API use.
- Inviting and approving members → `hosted-household-sharing`.

## Acceptance criteria

- `uv run pytest tests/unit/crypto -q` — keypair wrap/unwrap
  round-trip, sealed-box open with the right key and failure with
  another member's key, wrong passphrase fails, recovery unwrap, KDF
  params stored and honoured, `KeyRing` TTL and redaction
- `uv run pytest tests/unit/db/test_encrypted_text.py -q` — plaintext
  (`\x00`) and ciphertext (`\x01`) rows both read; AAD mismatch fails;
  blind index normalisation
- `uv run pytest tests/integration -q` with `KALETA_ENCRYPTION=passphrase`
  (fixture unlocks a test keyring) — the whole existing suite green on
  SQLite and on the Postgres job
- `uv run pytest tests/integration/test_encryption_at_rest.py -q` —
  after writing a transaction, a raw `SELECT description FROM
  transactions` returns bytes that do not contain the plaintext; after
  `KeyRing.lock`, the API returns `423`
- `uv run pytest tests/unit/services/test_transaction_search_budget.py -q`
  — 50 000-row search under the recorded budget
- `uv run python scripts/spec_coverage.py`
- `grep -c "KAL-ENC-" docs/bdd.md | grep -qE '^[1-9]'` — new area
  `KAL-ENC-*`: passphrase set at sign-up, unlock, wrong passphrase,
  recovery code, change passphrase, lock, privacy statement visible
- `./scripts/verify.sh --e2e`
- `[manual]` On Supabase: open the SQL editor, `SELECT name FROM
  t_xxx.accounts` — bytes only; `SELECT email, public_key, dek_sealed
  FROM public.tenant_members` — the address, a public key and opaque
  bytes, nothing else readable.

## Touchpoints

`src/kaleta/crypto/{__init__,keys,recovery,keyring}.py` (new),
`src/kaleta/db/types.py` (new), every model in the table above,
`src/kaleta/models/audit_log.py`, `src/kaleta/models/tenant.py`
(`TenantMember` key-material columns), `src/kaleta/models/local_key_material.py` (new),
`src/kaleta/services/{transaction,rule,account,dedupe,payee,category,tag,institution,personal_loan}_service.py`,
`src/kaleta/services/key_service.py` (new: unlock/change/recover),
`src/kaleta/auth/middleware.py` (unlock guard), `src/kaleta/api/deps.py`
(`423`), `src/kaleta/api/errors.py`, `src/kaleta/views/unlock.py` (new),
`src/kaleta/views/create_account.py`, `src/kaleta/views/settings/{security,privacy}_tab.py`,
`src/kaleta/config/settings.py` (`KALETA_ENCRYPTION`),
`alembic/versions/<new>_encrypted_columns.py`, `scripts/encrypt_database.py`
(new), `scripts/seed.py`, `scripts/reset_demo.py`, `pyproject.toml`
(`cryptography`; import-linter: `kaleta.crypto` sits below `kaleta.db`),
`src/kaleta/i18n/{en,pl}.json`, `docs/privacy-events.md` → rename to
`docs/privacy.md` with an "Encryption" section, `docs/tech-stack.md`,
`docs/bdd.md`, `SECURITY.md` (threat model paragraph).

## Open questions

- Argon2id parameters: 64 MiB per unlock is fine for one user at a time
  but a burst of logins on a small app host could exhaust memory —
  serialise unlocks with a semaphore, or settle for 32 MiB?
- Should "remember this device" exist (KEK-wrapped DEK in a secure
  cookie so the passphrase is asked once per device)? It weakens the
  at-rest story slightly (the cookie plus the database would suffice).
  Default no; revisit after dogfooding.
- Category and payee autocompletes currently query with `ILIKE` from
  the UI — confirm they already load the full (small) list and filter
  client-side; if not, they follow §4.
- The demo tenant is public and its passphrase is published — confirm
  that is acceptable or run the demo with `KALETA_ENCRYPTION=off` in a
  dedicated single-mode instance.

## Implementation notes

### Open questions — defaults taken

- **Argon2id cost**: kept the plan's `t=3, m=64 MiB, p=1`. Every derivation
  runs in a worker thread (it would otherwise stall the event loop) behind a
  process-wide `threading.Lock`, so a burst of unlocks costs time, never
  N × 64 MiB. A `threading.Lock`, not an `asyncio.Semaphore`: the latter
  binds to the first event loop that waits on it.
- **"Remember this device"**: not built (the plan's default no).
- **Category and payee autocompletes**: they load the full list through the
  services (`CategoryService.list`, `PayeeService.list`) and filter in the
  browser — no `ILIKE` from the UI; nothing to change.
- **Demo**: runs single mode with encryption off by default. When it runs
  with `KALETA_ENCRYPTION=passphrase`, `scripts/reset_demo.py` sets up (first
  reset) or opens the demo user's key with the published passphrase
  `demo-kaleta-data` (`--data-passphrase`), documented next to the demo login.

### Deviations and decisions

- **Blind index with encryption off.** The plan has `blind_index()` return
  `None` while encryption is off and the plain column carry the constraint.
  Instead the text columns are bytes in both modes and the indexes are
  computed under a fixed, public plaintext-mode key — one code path for
  equality and uniqueness, and switching encryption on is a rewrite of
  values and indexes rather than a schema change.
- **Name indexes are exact, not normalised.** `name_bidx` (payees, tags,
  institutions, categories, counterparties) is the HMAC of the name as
  written (`exact_index`). A normalised index would have made "LIDL" and
  "Lidl" collide — the very pairs the dedupe screens exist to find — and
  the migration fail on any database that holds them (verified: a database
  with both upgrades fine). Uniqueness and every lookup keep exactly the
  semantics the plain `==` had. The normalised `blind_index` (NFKC,
  casefold, collapsed whitespace — the plan's) serves the keys that were
  normalised already: payee identity keys and dismissed merchant keys.
  Account numbers get a digits index and an 8-digit suffix index (ADR-20).
- **Also encrypted, beyond the plan's table**: `payee_identities.pattern`
  (its `pattern_key` becomes the blind index of the casefolded key; the
  case-sensitive comparison happens in Python) and `payee_auto_merges`
  (`merged_name`, `snapshot` as `EncryptedJSON`) — both hold payee names.
  `EncryptedString` (the TOTP seed under `KALETA_SECRET_KEY`) is unchanged.
- **Queries moved to Python**: every `ORDER BY` on a name (`text_order.by_name`),
  transaction search (`SEARCH_SCAN_LIMIT` 100 000 rows per scan), rule
  matching, duplicate detection on import, transfer detection (suffix index,
  then `endswith` in Python), and report axes: saved reports and the report
  service group by **id** in SQL and name the groups in Python (categories
  sharing a name still merge into one row in the income statement, as
  before). Grouping on a name column next to its row's id (money flow)
  stays in SQL — that is grouping one row's own bytes.
- **Search budget** (acceptance, `tests/unit/services/test_transaction_search_budget.py`):
  50 000 encrypted transactions, 500 matches, first page + count, cold:
  101–123 ms on SQLite, 79–101 ms on Postgres 16 (Podman, M-series Mac).
  The first cut scanned twice (page, then count) and took 195–224 / 173–176
  ms locally — and 340 ms on the CI Postgres runner, over budget. The page's
  scan is now kept on the session for its count (`Session.info`, dropped at
  the next flush or rollback), so a search reads the table once. Under the
  300 ms budget, so no n-gram index.
- **Recovery lives on `/unlock`**, not on Settings → Security: the settings
  page renders every tab, and the others read data a locked session cannot.
  `/unlock` is the only page the guard exempts. Using the recovery code
  sets a new passphrase *and* issues a new code (the used one has been on
  screen).
- **Sign-up step 2** is the first visit to `/unlock` (hosted: the first
  sign-in after the e-mail is confirmed, when the account is provisioned);
  the "check your inbox" step says it is coming. The first member of an
  account generates the data key; a later one gets a keypair only and sees
  "Waiting for access" until the owner seals the key (sharing plan §2).
  An existing hosted tenant, or a self-hosted database switched on, is
  rewritten under the new key at that first set-up
  (`DataEncryptionService.rewrite_all`).
- **Key ring keying.** The ring is keyed by the browser's storage id. Sign-out
  and session expiry lock it; a session-id rotation *drops* the old entry
  rather than moving it (whoever completes the rotation may not be who
  unlocked). "Sign out everywhere" also drops every unlock of that member,
  so a bearer token cannot keep riding on a revoked browser.
- **API**: a bearer token rides on any live unlock of its member
  (`KeyRing.for_member`); otherwise `423 tenant_locked`. Bind-time errors
  arrive wrapped in SQLAlchemy's `StatementError`; `register_error_handlers`
  unwraps a domain error from it.
- **Backups** (plan §6): Settings → Data export decrypts (plaintext from the
  unlocked session); restore binds plaintext through the column types (so it
  re-encrypts) and recomputes every blind index (`db.blind_index.with_blind_indexes`).
  `local_key_material` is not backed up — a restore re-encrypts under the
  key the install already holds — and has no FK to `users`, since a restore
  empties `users` and a cascade would delete the only sealed data key. A
  restore whose users include no key holder is refused before anything is
  deleted. Scheduled on-disk backups (`VACUUM INTO`) copy ciphertext as is.
- **Scripts**: `seed.py`, `reset_demo.py` and `encrypt_database.py` unlock with
  `KALETA_DATA_PASSPHRASE` or a prompt (`scripts/data_passphrase.py`); with no
  key holder they stop with a message. `seed.py --fresh` keeps
  `local_key_material`. `encrypt_database.py` takes a plaintext backup
  first (its output says to delete it), prints the recovery code once, and
  `--decrypt` reverses everything (needed before downgrading past this
  revision, whose downgrade refuses while any ciphertext remains).
- **Migration** also drops the plain-text indexes earlier revisions put on
  columns it encrypts (`ix_payee_identities_pattern`,
  `ix_categorisation_rules_pattern`, `ix_import_rules_filename_pattern`).
  Tested upgrade → downgrade → upgrade on SQLite and Postgres 16 with
  case-variant names present.
- **Dismissed merchant keys** store only an index, so they cannot be
  rewritten under a new key: after switching encryption on, those dismissed
  candidates are offered once more. Accepted and documented.
- **`local_key_material`** is excluded from the audit log, like `user_mfa`.
- **Test suite under encryption**: `KALETA_ENCRYPTION=passphrase uv run pytest
  tests/unit tests/integration` runs green on SQLite and on Postgres. The
  autouse fixture stands in an unlocked keyring for services and browser
  sessions (`real_unlock` undoes the browser part for tests of the locked
  path); bearer tokens ride on a real `key_ring` entry for the API user;
  CLI tests give their file database a key holder sealing the suite's key
  (`tests/encryption_helpers.py`).
- **Manual acceptance (Supabase)**: verified by the owner on 2026-10-03 —
  the app ran against Supabase with encryption on and worked.
- **Docs**: `docs/images/encryption-overview.svg` explains the model in one
  picture at the top of `docs/privacy.md` (SVG rather than Mermaid: it
  renders the same on GitHub and in the MkDocs site, which has no Mermaid
  fence configured).
- **Docs**: `docs/privacy-events.md` is renamed `docs/privacy.md` (as the
  touchpoints say) and opens with the Encryption section; live links are
  updated, archived plans keep their old mention.
- **Not done**: a CI matrix entry for the encrypted run (parked in
  `docs/plans/chores.md`) (no workflow change in
  this plan's touchpoints); `Tenant.name` stays `Text` — nothing writes it
  yet, and it lives in the registry, outside any tenant's key.

## Implementation

Landed on 2026-10-03 (PR #185).

| SHA | Author | Date | Message |
|---|---|---|---|
| `7b70256` | Dawid Adamski | 2026-10-03 | Merge pull request #185 from DawidAdamski/plan/hosted-field-encryption |

**Files changed:**
- README.md
- SECURITY.md
- alembic/versions/r2s3t4u5v6w7_encrypted_columns.py
- docs/bdd.md
- docs/deployment.md
- docs/images/encryption-overview.svg
- docs/plans/chores.md
- docs/plans/hosted-field-encryption.md
- docs/privacy-events.md
- docs/privacy.md
- docs/tech-stack.md
- pyproject.toml
- scripts/data_passphrase.py
- scripts/encrypt_database.py
- scripts/reset_demo.py
- scripts/seed.py
- src/kaleta/api/deps.py
- src/kaleta/api/errors.py
- src/kaleta/auth/middleware.py
- src/kaleta/auth/session.py
- src/kaleta/auth/unlock.py
- src/kaleta/config/settings.py
- src/kaleta/crypto/__init__.py
- src/kaleta/crypto/keyring.py
- src/kaleta/crypto/keys.py
- src/kaleta/crypto/recovery.py
- src/kaleta/db/audit.py
- src/kaleta/db/blind_index.py
- src/kaleta/db/tenant_context.py
- src/kaleta/db/types.py
- src/kaleta/exceptions.py
- src/kaleta/i18n/locales/en.json
- src/kaleta/i18n/locales/pl.json
- src/kaleta/main.py
- src/kaleta/models/__init__.py
- src/kaleta/models/account.py
- src/kaleta/models/asset.py
- src/kaleta/models/audit_log.py
- src/kaleta/models/categorisation_rule.py
- src/kaleta/models/category.py
- src/kaleta/models/dismissed_candidate.py
- src/kaleta/models/import_rule.py
- src/kaleta/models/import_run.py
- src/kaleta/models/institution.py
- src/kaleta/models/local_key_material.py
- src/kaleta/models/payee.py
- src/kaleta/models/payee_identity.py
- src/kaleta/models/payee_merge.py
- src/kaleta/models/personal_loan.py
- src/kaleta/models/planned_transaction.py
- src/kaleta/models/report.py
- src/kaleta/models/reserve_fund.py
- src/kaleta/models/subscription.py
- src/kaleta/models/tag.py
- src/kaleta/models/transaction.py
- src/kaleta/models/yearly_plan.py
- src/kaleta/seeders/lookups.py
- src/kaleta/services/account_service.py
- src/kaleta/services/asset_service.py
- src/kaleta/services/backup_service.py
- src/kaleta/services/category_service.py
- src/kaleta/services/credit_service.py
- src/kaleta/services/data_encryption_service.py
- src/kaleta/services/dedupe_service.py
- src/kaleta/services/forecast_service.py
- src/kaleta/services/import_rule_service.py
- src/kaleta/services/import_service.py
- src/kaleta/services/institution_service.py
- src/kaleta/services/key_service.py
- src/kaleta/services/net_worth_service.py
- src/kaleta/services/payee_merge_service.py
- src/kaleta/services/payee_service.py
- src/kaleta/services/personal_loan_service.py
- src/kaleta/services/planned_price_drift_service.py
- src/kaleta/services/planned_transaction_service.py
- src/kaleta/services/report_service.py
- src/kaleta/services/rule_service.py
- src/kaleta/services/saved_report_service.py
- src/kaleta/services/subscription_service.py
- src/kaleta/services/tag_service.py
- src/kaleta/services/text_order.py
- src/kaleta/services/transaction_service.py
- src/kaleta/services/unplanned_radar_service.py
- src/kaleta/services/wizard_projection_service.py
- src/kaleta/views/create_account.py
- src/kaleta/views/settings/data_passphrase_card.py
- src/kaleta/views/settings/privacy_tab.py
- src/kaleta/views/settings/security_tab.py
- src/kaleta/views/unlock.py
- tests/conftest.py
- tests/e2e/test_encryption_unlock.py
- tests/e2e/test_tenant_signup.py
- tests/encryption_helpers.py
- tests/integration/conftest.py
- tests/integration/test_encrypt_database_script.py
- tests/integration/test_encryption_at_rest.py
- tests/integration/test_example_data.py
- tests/integration/test_payee_identities.py
- tests/integration/test_seed_payees_tags.py
- tests/integration/test_seed_payment_calendar.py
- tests/tenancy_helpers.py
- tests/unit/auth/test_unlock_guard.py
- tests/unit/crypto/__init__.py
- tests/unit/crypto/test_keys.py
- tests/unit/db/test_encrypted_text.py
- tests/unit/services/test_backup_service.py
- tests/unit/services/test_key_service.py
- tests/unit/services/test_transaction_search_budget.py
- tests/unit/services/test_transaction_service.py

**Acceptance criteria run:**

| Command | Exit |
|---|---|
| _(skipped: --fast, validated by PR CI)_ | – |

**Notes:** Partial coverage: none of the plan's Touchpoints matched the commit's changed files — verify the SHA.
