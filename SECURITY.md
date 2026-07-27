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
