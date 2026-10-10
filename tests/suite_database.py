# SPDX-License-Identifier: AGPL-3.0-or-later
"""The PostgreSQL database the suite runs against — one per pytest-xdist worker.

PostgreSQL is the only database (ADR-38). ``KALETA_DB_URL`` names it; unset,
the suite uses the server ``./scripts/test_db.sh up`` starts. Without a
reachable server the session stops with the sentence that says so.

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

from sqlalchemy.engine import URL, make_url

#: ``./scripts/test_db.sh url`` — keep the two in step.
DEFAULT_SUITE_DB_URL = "postgresql+asyncpg://kaleta:kaleta@127.0.0.1:55432/kaleta"
_START_ONE = "Start one: ./scripts/test_db.sh up"


class SuiteDatabaseUnavailableError(RuntimeError):
    """No PostgreSQL to run the suite against; the message says what to do."""


def suite_database_env() -> dict[str, str]:
    """``{"KALETA_DB_URL": …}`` for this process: the suite's database, or this worker's.

    Raises ``SuiteDatabaseUnavailableError`` for a non-PostgreSQL URL or a server
    that does not answer.
    """
    url = os.environ.get("KALETA_DB_URL") or DEFAULT_SUITE_DB_URL
    if not url.startswith("postgresql"):
        msg = f"The tests run on PostgreSQL only (ADR-38); KALETA_DB_URL is {url!r} {_START_ONE}"
        raise SuiteDatabaseUnavailableError(msg)
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    try:
        if worker:
            url = worker_database_url(url, worker)
        else:
            asyncio.run(_ping(_dsn(make_url(url))))
    except (OSError, ConnectionError) as exc:
        where = make_url(url).render_as_string(hide_password=True)
        msg = f"No PostgreSQL answers at {where} ({exc}); {_START_ONE}"
        raise SuiteDatabaseUnavailableError(msg) from exc
    return {"KALETA_DB_URL": url}


def suite_database_env_or_exit() -> dict[str, str]:
    """``suite_database_env()``, or end the pytest session with its sentence."""
    try:
        return suite_database_env()
    except SuiteDatabaseUnavailableError as exc:
        import pytest

        pytest.exit(str(exc), returncode=pytest.ExitCode.USAGE_ERROR)


def worker_database_url(url: str, worker: str) -> str:
    """Return ``url`` pointing at the worker's database, creating it if missing."""
    base = make_url(url)
    if not base.database:
        msg = f"KALETA_DB_URL names no database; pytest -n derives <database>_{worker} from it"
        raise RuntimeError(msg)
    name = f"{base.database}_{worker}"
    asyncio.run(_create_if_missing(_dsn(base), name))
    return base.set(database=name).render_as_string(hide_password=False)


def fresh_database_url(name: str) -> str:
    """An empty database ``<suite database>_<name>`` on the suite's server, for one app.

    The e2e servers each get one: dropped (with whoever is still connected)
    and created again, so a run never sees the last run's rows. Synchronous:
    Playwright's sync API keeps an event loop running in the test thread.
    """
    from sqlalchemy import create_engine, text

    base = make_url(os.environ["KALETA_DB_URL"])
    database = f"{base.database}_{name}"
    engine = create_engine(_sync(base), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        engine.dispose()
    return base.set(database=database).render_as_string(hide_password=False)


def query(url: str, sql: str) -> list[tuple[object, ...]]:
    """Rows of ``sql`` on the database at ``url`` — for e2e tests that look behind the app."""
    from sqlalchemy import create_engine, text

    engine = create_engine(_sync(make_url(url)))
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text(sql))]
    finally:
        engine.dispose()


def _sync(url: URL) -> URL:
    return url.set(drivername="postgresql+psycopg2", query={})


def _dsn(url: URL) -> str:
    # asyncpg takes a plain libpq URL: no driver suffix, no SQLAlchemy query options.
    return url.set(drivername="postgresql", query={}).render_as_string(hide_password=False)


async def _ping(dsn: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn, timeout=5)
    await conn.close()


async def _create_if_missing(dsn: str, name: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            # Another session may create it between the check and here.
            with contextlib.suppress(asyncpg.DuplicateDatabaseError):
                await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()
