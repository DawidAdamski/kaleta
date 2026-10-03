# Privacy

What Kaleta encrypts, what the operator can still see, and what the
app's anonymous error telemetry and bug reports capture.

## Encryption

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
