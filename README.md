# Kaleta

[![CI](https://github.com/DawidAdamski/kaleta/actions/workflows/ci.yml/badge.svg)](https://github.com/DawidAdamski/kaleta/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

**Kaleta** (Polish: *leather money pouch*) is a self-hosted personal budget and
finance app. Track transactions, build budgets, import bank CSV exports, and
forecast cash flow — from a browser, desktop window, or headless API.

![Kaleta dashboard (dark mode)](docs/design/dashboard-target.png)

## Quick start

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync && uv run kaleta
```

Open **http://localhost:8080**. On first launch the setup wizard creates the
database and runs migrations; on later starts the app auto-upgrades the
configured DB (from `~/.kaleta/config.json`) to the installed schema, with a
SQLite safety copy under `~/.kaleta/backups` first. Create your account, then
sign in. Optional demo data: `uv run python scripts/seed.py`.

Manual migrate (targets the live DB — bare `alembic upgrade head` uses
`KALETA_DB_URL` / cwd `kaleta.db`, which may differ from the configured one):

```bash
KALETA_MIGRATE_URL=sqlite+aiosqlite:///$HOME/path/to/kaleta.db uv run alembic upgrade head
```

## Documentation

- [Documentation site](https://dawidadamski.github.io/kaleta/) — product guides, architecture, roadmap
- [Getting started](docs/getting-started.md) — Docker, environment variables, development setup
- [Local deploy (launchd / systemd)](docs/deploy-local.md) — autostart on localhost + `/api/v1/health`
- [Contributing](CONTRIBUTING.md) — how we work and open a PR
- [Security](SECURITY.md) — report vulnerabilities privately

## License

The Kaleta core is licensed under [AGPL-3.0-or-later](LICENSE). External
contributors sign the [Contributor License Agreement](docs/cla.md) before their
first pull request is merged. See [ADR-033](docs/adr/033-agpl-core-with-cla.md)
for the open-core model.
