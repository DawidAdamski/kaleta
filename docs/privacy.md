# Privacy

What Kaleta encrypts, what the operator can still see, and what the
app's anonymous error telemetry and bug reports capture.

## Encryption

![How Kaleta keeps your data private: your data passphrase, or your recovery code, unlocks your private key in server memory while you are signed in; it opens the account's data key, which encrypts what you write. The database holds ciphertext for descriptions, payees, categories, names and notes, while amounts, dates and currencies stay readable.](images/encryption-overview.svg)

The picture in one paragraph: your data passphrase (or, if you lose it,
your recovery code) unlocks your private key, and only in the server's
memory, only while you are signed in. That key opens your account's data
key, which encrypts everything you write before it reaches the database
and decrypts it on the way back. What sits in the database — and in every
backup or dump of it — is ciphertext for the text and plain numbers for
amounts and dates. The sections below say exactly which is which.

### What is encrypted

Each member chooses a *data passphrase*, separate from their login
password. It unwraps an encryption key that lives only in server
memory while the member is signed in, and that key protects every
column a person writes free text into: account, payee, category, tag
and institution names; transaction descriptions and notes; split
notes; payee contact fields (address, e-mail, phone, website); saved
report names and configs; rule patterns; import filenames; yearly plan
lines; and audit log snapshots. Columns that need an equality check —
a unique name, an account-number match — use a keyed index stored
next to the ciphertext rather than the value itself.

### What the operator can see

[ADR-35](adr/035-hosted-multi-tenancy-and-user-held-encryption.md)
sets the limit precisely: the operator cannot read what any
transaction was for, with whom, on which account, in which category,
or any note, name, address or account number — not from the database
console, not from a backup, not from a dump. The operator can see the
shape of an account: how many accounts and transactions exist, their
amounts, dates, types and currencies, budget figures, and the e-mail
and user id.

### What the operator stores about an account

On the hosted instance, outside the account's own (encrypted) schema:

| What | Where | Why |
|---|---|---|
| Your user id at the identity provider and your e-mail address | Supabase Auth, and the `public` account registry | Signing in; mapping you to your account |
| Your role in the account and its status (active, suspended) | The registry | Who may do what |
| Key-wrapping material: your public key, your private key wrapped under your passphrase (and under your recovery code), a salt and the KDF parameters | The registry | Unlocking — none of it opens anything without your passphrase or recovery code |
| When the account was created and last used | The registry | Operating the service |
| Anonymous error events | Your account's own schema | Fixing bugs; no content, see below |
| Bug reports, only if you send one | Your account's own schema | What you chose to send, in the clear |

Your password itself is held by the identity provider (Supabase Auth) as a
hash; Kaleta never stores it.

### What stays in the clear on purpose

Amounts, dates, currencies, enum values, colours, icons and foreign
keys stay unencrypted — SQL needs to aggregate, filter and sort them.
So does data that is not financial content: display names and e-mail
addresses, the fields in a bug report (you choose to send those to
the operator in the clear — see below), and the two-factor secret,
which is already encrypted separately under `KALETA_SECRET_KEY` (see
[SECURITY.md](../SECURITY.md)).

### Passphrase and recovery code

At first sign-in you choose the data passphrase (minimum 12
characters) and are shown a 26-character recovery code once, with the
option to copy or download it; you must tick "I have saved my
recovery code" before continuing. Losing both the passphrase and the
recovery code means your data cannot be recovered — nobody, including
the operator, holds a spare key. "Forgot it? Use your recovery code"
on `/unlock` sets a new passphrase and issues a new recovery code; the
used one stops working. Settings → Security lets you change the
passphrase, check whether a recovery code exists, generate a new one,
and lock your data immediately ("Lock now").

### Locking

The decryption key exists only in server memory for the length of a
signed-in session. Signing out, a session rotation, "Lock now" and
"Sign out everywhere" all drop it; so does a server restart or another
replica, which is why every session has to unlock again after one. An
API bearer token cannot unlock data by itself — it only works while
its member has an unlocked browser session elsewhere; otherwise the
API answers `423 Locked` with error code `tenant_locked`.

### Limits of this model

This is encryption at rest under a key the operator does not hold —
not end-to-end encryption. While a member is signed in, the server
holds that key in memory to compute budgets, forecasts and search
results, so a compromised app host could capture it during that
window. The model defends against the realistic operator-side risks —
database access, backups, exports, a leaked connection string — not
against a compromised server.

The data export you download from Settings → Data is the exception by
design: it is your own copy, written in plain form from your unlocked
session, so keep it as carefully as the passphrase. Restoring it
encrypts everything again.

Self-hosted installs can turn the same protection on for their SQLite
or PostgreSQL database; see
[Field-level encryption](tech-stack.md#field-level-encryption) in
`docs/tech-stack.md`.

### Deletion and retention

The owner deletes the account from Settings → Data → *Delete my account*
(the data passphrase is required, and the members who lose access are shown
first); the operator can do the same with `scripts/tenant_admin.py delete`.
Either way every member's sign-in identity is removed from Supabase Auth,
then the account's schema and its registry rows are dropped. A member who is
not the owner leaves the household instead, which removes only their own
identity.

What remains afterwards: the database provider's backups, for as long as
the instance's backup retention (see
[deployment.md](deployment.md#backups) — 7 days of daily backups, or up to
28 days with point-in-time recovery); those copies hold the same ciphertext,
so they are as unreadable without a passphrase as the live data was. The
operator's audit line for a deletion records the account id, the schema name
and how many identities were removed — no e-mail address. Error events and
bug reports live in the account's own schema, so they go with it. On a
self-hosted install they expire after `KALETA_EVENT_RETENTION_DAYS` (7 by
default) and `KALETA_BUG_REPORT_RETENTION_DAYS` (90); on the hosted instance
that sweep does not run per account yet, so they are kept until the account
is deleted.

## Anonymous error events

Kaleta can record **anonymous error events** on the instance database so
maintainers can debug hosted failures without access to your financial
data.

### What is captured

Each event stores:

- Short **event ID** (shown in the UI when a server error occurs)
- Timestamp, route, exception class name
- Hash and truncated stack trace (**`src/kaleta` code frames only**)
- Application version
- Opaque session / user identifiers (numeric user id or NiceGUI client id)

### What is never captured

The schema has **no free-text field** for user data. We never store:

- Request bodies or query parameters
- Transaction descriptions, amounts, or payees
- Account names or category labels

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `KALETA_EVENTS_ENABLED` | `true` | Instance-level capture on/off |
| `KALETA_EVENT_RETENTION_DAYS` | `7` | Rolling deletion window |

Per-user opt-out: **Settings → Privacy & diagnostics → Capture anonymous
error events**.

### Bug reports

When something fails, the error tray offers **Report** — or use
**Report a problem** in the account menu, or Settings → Privacy &
diagnostics. What a report contains is listed in the dialog before you
send it:

- the summary and description **you type** (free text — write only what you
  are willing to share; it is stored unencrypted as operator data),
- an optional contact e-mail (blank by default),
- the error IDs from this session (removable, one chip each),
- the app version, the page you were on, your browser, window size and
  language,
- **only if you tick the box**: the last 200 log lines of your session,
  redacted — no amounts, payees, descriptions or account names.

Nothing is read from your ledger. Reports are kept for
`KALETA_BUG_REPORT_RETENTION_DAYS` (default 90) and then deleted. You can
withdraw any report yourself at any time: Settings → Privacy &
diagnostics → *Your reports* → delete. A self-hosted instance stores
reports in its own database; a hosted instance may forward them to the
maintainer (webhook or e-mail, see below), which is when the words you
typed leave the instance.

A report is rate-limited to 5 per session per hour.

#### Where a report goes

| Variable | Default | Meaning |
|---|---|---|
| `KALETA_BUG_REPORT_WEBHOOK` | *(unset)* | `POST` the report JSON to an n8n or generic endpoint |
| `KALETA_BUG_REPORT_WEBHOOK_INCLUDE_LOGS` | `false` | Include the log excerpt in that POST |
| `KALETA_BUG_REPORT_EMAIL` + `KALETA_SMTP_*` | *(unset)* | Also e-mail the report |
| `KALETA_BUG_REPORT_RETENTION_DAYS` | `90` | Rolling deletion window |

With neither configured the report only lands in the instance database.
The maintainer reads it with:

```bash
scripts/bug_reports.py list
scripts/bug_reports.py show <report_id>
scripts/bug_reports.py close <report_id> --ref <issue url>
```

The confirmation dialog's **Open a GitHub issue** button prefills the
report ID, version, page and error IDs — never your description and never
the log excerpt.

### Structured logs

`KALETA_LOG_FORMAT=json` writes one JSON object per line carrying
`request_id`, `session_id`, `route`, `event_id` and `app_version`, so an
event ID leads to the lines around it. Every record is redacted before it
is written: bearer tokens, e-mail addresses, query strings and arguments
longer than 200 characters. Logs go to stdout only — the host ships them.

### Optional error tracker

`KALETA_ERROR_TRACKER_DSN` (extra: `tracker`) forwards the same anonymous
event to a Sentry-protocol endpoint such as a self-hosted GlitchTip. It is
**off by default**, and a `before_send` scrubber strips everything except
the exception type, the redacted frames, the route and the event ID.

### Looking up an event by hand

When you see an error toast with an **Event ID**, copy it and include it
in your GitHub issue or email. The maintainer can look up the trace with:

```sql
SELECT occurred_at, level, route, exception_class, stack_trace, app_version
FROM app_events
WHERE event_id = 'XXXXXXXX';
```

(On Supabase: SQL Editor → New query.)

### Hosted instance

See also [deployment.md](deployment.md) for Supabase Postgres setup.

### Related plan

[`docs/plans/archive/observability-anonymous-events.md`](plans/archive/observability-anonymous-events.md)
