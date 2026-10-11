# Kaleta

[![CI](https://github.com/DawidAdamski/kaleta/actions/workflows/ci.yml/badge.svg)](https://github.com/DawidAdamski/kaleta/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Kaleta** (Polish: *leather money pouch*) is a self-hosted personal budget and
finance app. Track transactions, build budgets, import bank CSV exports, and
forecast cash flow — from a browser (installable as an app) or a headless API.

![Kaleta dashboard (dark mode)](docs/design/screenshot.png)

## Quick start

Kaleta runs on PostgreSQL 16+ ([ADR-38](docs/adr/038-postgresql-only-one-tenancy-layout.md)).
The shortest way is the Compose stack — Kaleta plus PostgreSQL 18, with the
database password and the session key generated on the first start:

```bash
podman compose up -d --build     # or: docker compose up -d --build
```

Open http://localhost:8080. The first sign-up on an empty instance creates the
instance administrator and the first family, then asks for a data passphrase.
Forgotten password: `podman compose exec kaleta uv run kaleta-admin
reset-password <e-mail>`. For HTTPS (to install the app on a phone), nightly
backups, a restore drill and upgrades, follow the
[self-hosting guide](docs/self-hosting.md).

Without containers: Python 3.13+, [uv](https://docs.astral.sh/uv/) and a
PostgreSQL you point `KALETA_DB_URL` at (`postgresql://user:pass@host/db`).
Kaleta brings the database to the current schema on every start.

```bash
uv sync && KALETA_DB_URL=postgresql://kaleta:…@localhost/kaleta uv run kaleta
```

Optional demo data: `uv run python scripts/seed.py` — six years of
transactions named by merchant and tagged by payment method, with budgets,
assets and a payment calendar of recurring commitments.

## Hosted Kaleta

A hosted instance (Supabase sign-in, one account per household) is being
rolled out; its address will be listed here once it is public. **The privacy
promise:** everything you write — descriptions, payees, categories, names,
notes — is encrypted under a key that only your data passphrase or recovery
code opens, and only in the server's memory while you are signed in. The
operator, a database dump and every backup see ciphertext for that text, and
plain amounts and dates. Deleting your account removes its data and your
sign-in. Details: [docs/privacy.md](docs/privacy.md); running one yourself:
[docs/deployment.md](docs/deployment.md).

## Optional forecasting

The Forecast view works out of the box with a seasonal-naive projection.
For the advanced model, install [Prophet](https://facebook.github.io/prophet/)
as an optional extra (~300 MB with cmdstan) and restart:

```bash
uv sync --extra forecast
```

Docker users: the `kaleta:full` image ships Prophet; `kaleta:slim` uses
the naive fallback.

## Documentation

- [Documentation site](https://dawidadamski.github.io/kaleta/) — product guides, architecture, roadmap
- [Getting started](docs/getting-started.md) — Docker/Podman volumes, environment variables, development
- [Hosted deployment (Supabase)](docs/deployment.md) — multi-tenant instance, operations, hosted-dev stack, demo
- [Privacy](docs/privacy.md) — what is encrypted, anonymous error events, retention, bug reports
- [Local deploy (launchd / systemd)](docs/deploy-local.md) — autostart on localhost + `/api/v1/health`
- [Contributing](CONTRIBUTING.md) — how we work and open a PR
- [Security](SECURITY.md) — report vulnerabilities privately

## License

The Kaleta core is licensed under [AGPL-3.0-or-later](LICENSE). External
contributors sign the [Contributor License Agreement](docs/cla.md) before their
first pull request is merged. See [ADR-033](docs/adr/033-agpl-core-with-cla.md)
for the open-core model.
