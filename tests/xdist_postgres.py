# SPDX-License-Identifier: AGPL-3.0-or-later
"""One PostgreSQL database per pytest-xdist worker.

Under ``pytest -n`` every worker runs the truncate-once + rolled-back
connection isolation of ``tests/conftest.py`` against a database of its own,
``<database>_<worker id>``, created on first use and migrated to head. The
databases are kept between runs (the next session truncates them), so only the
first parallel run pays for ``CREATE DATABASE`` and the migrations.

Imported by ``tests/conftest.py`` before ``kaleta`` is, because the settings
read ``KALETA_DB_URL`` at import time.

The role in ``KALETA_DB_URL`` needs ``CREATEDB``. Two pytest sessions at once
against the same server (say ``verify.sh`` and the pre-push hook) share these
databases and truncate each other's rows — run one at a time, or point the
second at another database name.
"""

import asyncio
import contextlib
import os

from sqlalchemy.engine import make_url


def worker_database_env() -> dict[str, str]:
    """``{"KALETA_DB_URL": <worker database>}`` under xdist on Postgres, else ``{}``."""
    url = os.environ.get("KALETA_DB_URL", "")
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker or not url.startswith("postgresql"):
        return {}
    return {"KALETA_DB_URL": worker_database_url(url, worker)}


def worker_database_url(url: str, worker: str) -> str:
    """Return ``url`` pointing at the worker's database, creating it if missing."""
    base = make_url(url)
    if not base.database:
        msg = f"KALETA_DB_URL names no database; pytest -n derives <database>_{worker} from it"
        raise RuntimeError(msg)
    name = f"{base.database}_{worker}"
    # asyncpg takes a plain libpq URL: no driver suffix, no SQLAlchemy query options.
    dsn = base.set(drivername="postgresql", query={}).render_as_string(hide_password=False)
    asyncio.run(_create_if_missing(dsn, name))
    return base.set(database=name).render_as_string(hide_password=False)


async def _create_if_missing(dsn: str, name: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            # Another session may create it between the check and here.
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
