# Security Policy

## Supported versions

Kaleta is under active development. Only the `main` branch receives security
fixes. Tagged releases will be added to this table when the project starts
shipping versioned releases.

| Version | Supported |
| ------- | --------- |
| `main`  | Yes       |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately using [GitHub Security Advisories](https://github.com/DawidAdamski/kaleta/security/advisories/new)
for this repository (preferred), or email **TODO-project-alias** if you cannot
use GitHub.

Include:

- A description of the issue and its impact
- Steps to reproduce (proof-of-concept if possible)
- Affected version or commit (`main` branch SHA if known)

## Response pledge

We aim to acknowledge reports within **14 days** and will keep you informed of
progress toward a fix. We may request additional information to reproduce or
assess severity.

## Disclosure

We prefer coordinated disclosure. Please allow reasonable time for a fix before
public discussion. We will credit reporters in the advisory when they wish to
be named.

## Forgotten password (local logins)

Kaleta does not offer email or in-app password recovery for local logins
(`KALETA_AUTH_BACKEND=local`, the default). If you forget your password, the
instance operator resets it from a shell:

```bash
uv run kaleta-admin reset-password <e-mail>
```

This updates the argon2 password hash of that member in
`public.local_identities` and signs every browser session of that member out.
The command refuses to run for an e-mail address that has no local login.
(`kaleta --reset-password` no longer exists; it exits with status 2 and points
to this command.)

**Sessions and tokens:** resetting the password signs every browser out. So
does turning two-factor on or off and reissuing recovery codes — except the
browser that made the change — and **Settings → Security → Sign out
everywhere** does it on demand, that browser included. Each of these moves a
per-user watermark (`users.sessions_valid_from`); a session that signed in
before it is refused on its next page load or cookie API call. The app process
caches the watermark for up to 60 seconds, so a reset run from a shell, or a
change made on another replica, takes effect within a minute. API bearer
tokens are **not** affected: revoke them in Settings.

## Two-factor authentication

A second factor is optional and off until you turn it on in
**Settings → Security**. Kaleta implements TOTP (RFC 6238, 30-second steps,
one step of clock drift either way) — the same thing Google Authenticator,
1Password, Aegis and the rest speak.

What it guards:

- **Signing in.** After the password is accepted the session is *pending*: it
  carries no authentication at all until a code is given, so a pending session
  reaches no page and no `/api/v1` route.
- **Creating or revoking an API bearer token.** A token outlives the browser
  session that made it, so it asks for a current code when it has been more
  than 10 minutes since the last one.
- **Reissuing recovery codes**, on the same terms. Ten fresh codes are ten
  fresh ways past the factor.

What it does not guard:

- **Using** an API bearer token. A token is a separate credential and a
  request carrying one is never challenged — revoke the token instead.
- **Restoring a backup.** A restore replaces every table, `user_mfa`
  included, so restoring a backup taken before you switched the factor on
  turns it off — and restores that backup's password hash with it. It asks
  for nothing but a signed-in session. Treat a backup file as equivalent to
  the password and the factor together: anyone who can upload one to your
  instance, and anyone who holds one, has both. This is the same trust a
  backup has always carried in Kaleta; two-factor authentication does not
  narrow it.

**Recovery codes.** Enrolling hands you ten one-time codes, stored as argon2
hashes. Each works once, anywhere a code is asked for. Asking to see them
again issues a fresh set and invalidates the old one.

**The TOTP secret at rest** is encrypted with AES-256-GCM under a key derived
from `KALETA_SECRET_KEY`. With `KALETA_DEBUG=true` that variable may be left
unset, and it then falls back to a constant compiled into the source — so on a
debug install the secret is, for all practical purposes, stored in the clear.
That is the point of the check that refuses the default key when debug is off;
do not run a real ledger with debug on. Rotating that variable therefore makes every existing
enrolment unreadable; see below for the way out.

**Wrong codes are rate-limited** — five in a row locks the code prompt for
fifteen minutes, counted per account. That cuts both ways: someone who knows
your password but not your codes can keep you out of the prompt for fifteen
minutes at a time. Counting per IP address instead would let anyone with a
handful of addresses walk past the limit altogether, which is the worse of the
two, so the lockout is the trade we take. The same counter covers all four prompts that
take a code — the login code prompt, the step-up dialog, the "turn it off"
dialog and the confirm step of setting a factor up — so five wrong answers in
any one of them locks the other three. The pairing that bites in practice is
the step-up and "turn it off" dialogs, both reachable while the factor is on:
wrong answers in one lock the code prompt you need at the next sign-in. (The
setup dialog shares the bucket too, but locking yourself out there only delays
enrolling — there is no factor yet for a login to ask about.)

**Locked out with shell access** (no phone, no recovery codes):

```bash
uv run kaleta-admin reset-password <e-mail> --disable-mfa
```

This removes every second-factor enrolment of that member along with setting the new password.
Without the flag a password reset leaves the second factor exactly as it was —
resetting a password must not be a way around it.

## Field-level encryption

Kaleta can encrypt every column a person writes free text into — names,
descriptions, notes, contact details and more — under a key derived from a
*data passphrase* that only the signed-in member holds (see
[docs/privacy.md](docs/privacy.md#encryption) and
[ADR-35](docs/adr/035-hosted-multi-tenancy-and-user-held-encryption.md)).
This protects against someone who only has the database file, a backup, a
dump, or a leaked connection string. It does **not** protect against a
compromised app host: the server decrypts rows while a member is signed in,
so a key can be captured from process memory during that window. Losing both
the passphrase and the recovery code makes that member's data unrecoverable —
there is no server-side master key to fall back to.

Encryption is always on (`KALETA_ENCRYPTION=passphrase` is the default).
`KALETA_ENCRYPTION=off` is accepted only with `KALETA_DEBUG=true`. A family
that already holds data from before encryption is encrypted when its first data
passphrase is set up: that step re-encrypts every row and blind index and shows
a recovery code once — save it.
