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

## Forgotten password (local single-user)

Kaleta is single-user and does not offer email or in-app password recovery.
If you forget your password on a local install:

```bash
uv run kaleta --reset-password
```

This updates the argon2 password hash for the sole user in the database
configured in `~/.kaleta/config.json`. The command refuses to run when no user
exists (complete first-run bootstrap instead) or when more than one user row is
present.

**Sessions and tokens:** resetting the password does **not** invalidate existing
NiceGUI browser sessions or API bearer tokens. Sign out (or clear site data) and
revoke tokens in Settings if you need to force re-authentication after a reset.

## Two-factor authentication

A second factor is optional and off until you turn it on in
**Settings → Security**. Kaleta implements TOTP (RFC 6238, 30-second steps,
one step of clock drift either way) — the same thing Google Authenticator,
1Password, Aegis and the rest speak.

What it guards:

- **Signing in.** After the password is accepted the session is *pending*: it
  carries no authentication at all until a code is given, so a pending session
  reaches no page and no `/api/v1` route.
- **API bearer tokens.** A token outlives the browser session that made it, so
  creating or revoking one asks for a current code when it has been more than
  10 minutes since the last one.

What it does not guard: API bearer tokens themselves. They are a separate
credential and requests carrying one are never challenged — revoke the token
instead.

**Recovery codes.** Enrolling hands you ten one-time codes, stored as argon2
hashes. Each works once, anywhere a code is asked for. Asking to see them
again issues a fresh set and invalidates the old one.

**The TOTP secret at rest** is encrypted with AES-256-GCM under a key derived
from `KALETA_SECRET_KEY`. Rotating that variable therefore makes every existing
enrolment unreadable; see below for the way out.

**Wrong codes are rate-limited** — five in a row locks the code prompt for
fifteen minutes, counted per account. That cuts both ways: someone who knows
your password but not your codes can keep you out of the prompt for fifteen
minutes at a time. Counting per IP address instead would let anyone with a
handful of addresses walk past the limit altogether, which is the worse of the
two, so the lockout is the trade we take.

**Locked out with shell access** (no phone, no recovery codes):

```bash
uv run kaleta --reset-password --disable-mfa
```

This removes every second-factor enrolment along with setting the new password.
Without the flag a password reset leaves the second factor exactly as it was —
resetting a password must not be a way around it.
