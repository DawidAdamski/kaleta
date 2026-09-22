---
adr_id: "036"
title: "Local Column Encryption and TOTP as Base Dependencies"
status: accepted
---

# ADR-36: Local Column Encryption and TOTP as Base Dependencies

- **Decision**: Two-factor authentication ships in every install, not in an
  extra. `pyotp` (TOTP), `qrcode` (the enrolment QR as inline SVG) and
  `cryptography` (AES-256-GCM) become base dependencies. Secrets that must be
  readable again — today only `user_mfa.totp_secret` — are stored through
  `EncryptedString` in `kaleta/db/types.py`: a `TypeDecorator[str]` over
  `LargeBinary` whose payload is a one-byte format marker, a 12-byte nonce and
  an AES-256-GCM ciphertext authenticated against the column's qualified name.
  The key comes from a module-level *key source*, which derives it from
  `KALETA_SECRET_KEY` with HKDF-SHA256.
- **Rationale**: A second factor that a self-hoster has to install an extra to
  get is a second factor most self-hosters will not have, and the whole point
  of the feature is that it guards the default install. The TOTP secret is the
  one piece of Kaleta's data that is *equivalent to a credential* — anyone
  holding it can mint valid codes forever — so leaving it in plain text beside
  the argon2 password hash would make the second factor worth roughly what the
  first one is worth to whoever has the database file. Encrypting it needs a
  cipher, and the standard library has none.
  [ADR-35](035-hosted-multi-tenancy-and-user-held-encryption.md) already
  records `cryptography` as a base dependency for the hosted work; this is
  that decision arriving one plan earlier, in a form the hosted plan can adopt
  rather than replace.
- **Rejected alternative**: a keystream built from `hmac` and `hashlib`, which
  would have added no dependency at all. Rejected because it means owning an
  AEAD construction — nonce discipline, tag comparison, format versioning —
  for the one value in the app where getting it wrong costs the most. Also
  rejected: storing the secret in plain text on the grounds that the
  self-hoster already owns the file. That reasoning holds for a stolen laptop
  and fails for every backup, sync folder and cloud snapshot the file passes
  through.
- **Consequence**: **Rotating `KALETA_SECRET_KEY` makes every existing
  enrolment unreadable**, and the way back is
  `kaleta --reset-password --disable-mfa` followed by re-enrolling.
  `SECURITY.md` and `docs/tech-stack.md` both say so. The key source is
  swappable (`set_key_source`) so the per-tenant key ring from ADR-35 can
  replace the derivation without touching a model, and the reader already
  accepts the format byte `\x00` (plain UTF-8) that ADR-35's
  `KALETA_ENCRYPTION=off` generation will write, so rows written now are not
  orphaned by that change. Two knock-on rules follow from the column being a
  BLOB: `user_mfa` is excluded from the audit log, which serialises rows
  through the ORM and would have copied the decrypted secret into
  `audit_log`; and `BackupService` base64-encodes binary columns on export and
  restores them as the ciphertext they are, so a backup carries no readable
  secret and a restore does not re-encrypt one.
