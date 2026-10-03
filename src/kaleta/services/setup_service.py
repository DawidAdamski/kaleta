# SPDX-License-Identifier: AGPL-3.0-or-later
"""First-run database setup — migrations and engine configuration."""

from __future__ import annotations

import asyncio
import logging
import os
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from alembic import command
from kaleta.exceptions import MigrationError

logger = logging.getLogger(__name__)


#: The registry's own version table (``alembic_public/``), next to the
#: tenant schemas' ``alembic_version``.
PUBLIC_VERSION_TABLE = "alembic_version_public"


def _alembic_ini(*, public: bool = False) -> Path:
    name = "alembic_public.ini" if public else "alembic.ini"
    return Path(__file__).resolve().parents[3] / name


def _alembic_config(*, schema: str | None = None, public: bool = False) -> Config:
    """Alembic config for the tenant history (optionally one schema) or the registry.

    ``schema`` reaches ``alembic/env.py`` as ``-x tenant_schema=…``, exactly as
    it would from the command line.
    """
    config = Config(str(_alembic_ini(public=public)))
    if schema is not None:
        from kaleta.db.tenant_schemas import require_valid_schema_name

        config.cmd_opts = Namespace(x=[f"tenant_schema={require_valid_schema_name(schema)}"])
    return config


def _script_directory(*, public: bool = False) -> ScriptDirectory:
    return ScriptDirectory.from_config(_alembic_config(public=public))


def _sync_url(db_url: str) -> str:
    """Swap async drivers for sync ones so sync SQLAlchemy can open the DB.

    PostgreSQL names ``psycopg2`` explicitly: since SQLAlchemy 2.1 a bare
    ``postgresql://`` URL means psycopg 3, which the ``postgres`` extra does
    not install.

    The TLS option is spelled differently by the two drivers: asyncpg takes
    ``?ssl=require`` (what ``docs/deployment.md`` tells hosted installs to
    use), psycopg2 only ``?sslmode=require`` and refuses the URL otherwise.
    """
    sync = db_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
    url = make_url(sync)
    if url.get_backend_name() != "postgresql" or "ssl" not in url.query:
        return sync
    ssl = url.query["ssl"]
    mode = ssl if isinstance(ssl, str) else ssl[-1]
    # asyncpg also accepts booleans for `ssl`.
    mode = {"true": "require", "false": "disable"}.get(mode.lower(), mode)
    query = {k: v for k, v in url.query.items() if k != "ssl"}
    query.setdefault("sslmode", mode)
    return url.set(query=query).render_as_string(hide_password=False)


def head_revision(*, public: bool = False) -> str:
    """Return the alembic head revision for the installed code.

    ``public=True`` asks about the tenant registry's history instead.
    """
    head = _script_directory(public=public).get_current_head()
    if head is None:
        raise MigrationError("No alembic head revision found in this installation")
    return head


def _revision_target(db_url: str, schema: str | None, public: bool) -> tuple[str, dict[str, str]]:
    """The URL to open and the MigrationContext options that find the version table.

    On SQLite a schema is a file of its own (``kaleta.db.tenant_schemas``), so
    the URL moves and the version table stays unqualified.
    """
    from kaleta.db.tenant_schemas import PUBLIC_SCHEMA, is_sqlite_url, sqlite_schema_file

    opts: dict[str, str] = {}
    if public:
        opts["version_table"] = PUBLIC_VERSION_TABLE
    if not is_sqlite_url(db_url):
        if schema is not None:
            opts["version_table_schema"] = schema
        return db_url, opts
    target = PUBLIC_SCHEMA if public else schema
    if target is None:
        return db_url, opts
    return "sqlite:///" + str(sqlite_schema_file(db_url, target)), opts


def current_revision(db_url: str, *, schema: str | None = None, public: bool = False) -> str | None:
    """Return the DB's alembic revision, or None if unstamped / empty.

    ``schema`` reads one tenant schema's version; ``public`` the registry's.
    """
    from alembic.runtime.migration import MigrationContext

    url, opts = _revision_target(db_url, schema, public)
    engine = create_engine(_sync_url(url))
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts=opts)
            return context.get_current_revision()
    finally:
        engine.dispose()


def upgrade_to_head(db_url: str, *, schema: str | None = None) -> None:
    """Run Alembic ``upgrade head`` against ``db_url`` (synchronous).

    ``schema`` migrates that one tenant schema of a multi-tenant database; it
    must already exist (``TenantService`` creates it).
    """
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.upgrade(_alembic_config(schema=schema), "head")
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)


def upgrade_public_to_head(db_url: str) -> None:
    """Bring the tenant registry (``alembic_public/``) to head (synchronous)."""
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.upgrade(_alembic_config(public=True), "head")
    finally:
        os.environ.pop("KALETA_MIGRATE_URL", None)


def _pre_migration_safety_copy(db_url: str) -> Path | None:
    """VACUUM INTO a timestamped file when the URL points at an on-disk SQLite DB."""
    from kaleta.config import settings
    from kaleta.services.scheduled_backup_service import ScheduledBackupService

    url = make_url(db_url)
    if url.get_backend_name() != "sqlite":
        logger.warning(
            "Auto-migrating non-SQLite database without an automatic safety copy. "
            "Take a manual backup before upgrading if this is production data."
        )
        return None

    database = url.database
    if not database or database == ":memory:" or database.startswith("file::memory:"):
        return None

    source = Path(database)
    if not source.is_file():
        return None

    svc = ScheduledBackupService(
        db_url=db_url,
        backup_dir=Path(settings.backup_dir),
        retain=settings.backup_retain,
    )
    path = svc.create_backup()
    if path is not None:
        logger.info("Pre-migration safety copy written to %s", path)
    return path


def ensure_schema_current(db_url: str) -> None:
    """Bring ``db_url`` to alembic head, or refuse with a clear error.

    When the database is behind head, takes a SQLite ``VACUUM INTO`` safety
    copy (via scheduled backup settings) before upgrading. No-op when already
    at head.
    """
    head = head_revision()
    try:
        current = current_revision(db_url)
    except Exception as exc:
        raise MigrationError(
            f"Could not read alembic revision for {db_url!r}: {exc}. "
            "Fix the database URL in ~/.kaleta/config.json or migrate manually with "
            f"KALETA_MIGRATE_URL=<url> uv run alembic upgrade head (expected head: {head})."
        ) from exc

    if current == head:
        logger.debug("Database schema already at head %s", head)
        return

    if current is not None:
        script = _script_directory()
        try:
            known = script.get_revision(current)
        except Exception as exc:
            known = None
            unknown_exc: BaseException | None = exc
        else:
            unknown_exc = None
        if known is None:
            raise MigrationError(
                f"Database is at unknown alembic revision {current!r}; installed head is "
                f"{head!r}. Refusing to start — restore a backup or upgrade the app to a "
                "build that knows this revision. Manual migrate: "
                "KALETA_MIGRATE_URL=<url> uv run alembic upgrade head"
            ) from unknown_exc

    safety = _pre_migration_safety_copy(db_url)
    logger.info(
        "Database schema at %s; upgrading to head %s%s",
        current or "(unstamped)",
        head,
        f" (safety copy: {safety})" if safety else "",
    )
    try:
        upgrade_to_head(db_url)
    except Exception as exc:
        hint = f" Safety copy is at {safety}." if safety else ""
        raise MigrationError(
            f"Failed to upgrade database from {current!r} to head {head!r}: {exc}.{hint} "
            "Manual migrate: KALETA_MIGRATE_URL=<url> uv run alembic upgrade head"
        ) from exc

    after = current_revision(db_url)
    if after != head:
        hint = f" Safety copy is at {safety}." if safety else ""
        raise MigrationError(
            f"After upgrade, database revision is {after!r} but head is {head!r}.{hint} "
            "Manual migrate: KALETA_MIGRATE_URL=<url> uv run alembic upgrade head"
        )


async def run_migrations(db_url: str) -> None:
    """Run Alembic migrations in a thread-pool executor (synchronous Alembic API)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, upgrade_to_head, db_url)


async def activate_database(db_url: str, *, name: str) -> None:
    """Run migrations, configure the engine, and persist the chosen database."""
    from kaleta.config import settings
    from kaleta.config.setup_config import save_db
    from kaleta.db import configure_database
    from kaleta.services.scheduled_backup_service import ScheduledBackupService

    await run_migrations(db_url)
    configure_database(db_url, debug=settings.debug)
    save_db(db_url, name=name)

    # Immediate first snapshot so a freshly activated DB is protected before
    # the scheduler's next tick (and even if the interval has not elapsed).
    try:
        ScheduledBackupService(
            db_url=db_url,
            backup_dir=Path(settings.backup_dir),
            retain=settings.backup_retain,
        ).run_once()
    except Exception:
        logger.exception("Post-activation backup failed for %s", db_url)


# ── KALETA_TENANCY=multi ──────────────────────────────────────────────────────


def _registry_url_and_table(db_url: str) -> tuple[str, str]:
    from kaleta.db.tenant_schemas import PUBLIC_SCHEMA, is_sqlite_url, sqlite_schema_file

    if is_sqlite_url(db_url):
        return "sqlite:///" + str(sqlite_schema_file(db_url, PUBLIC_SCHEMA)), "tenants"
    return db_url, f"{PUBLIC_SCHEMA}.tenants"


def tenant_schema_names(db_url: str) -> list[str]:
    """Every tenant schema the registry knows of, except those being deleted."""
    from sqlalchemy import text

    from kaleta.db.tenant_schemas import is_valid_schema_name

    url, table = _registry_url_and_table(db_url)
    engine = create_engine(_sync_url(url))
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT schema_name FROM {table} WHERE status != 'deleting' ORDER BY id")  # noqa: S608 — constant table name
            )
            names = [str(row[0]) for row in rows]
    finally:
        engine.dispose()
    return [name for name in names if is_valid_schema_name(name)]


def tenants_pending_migration(db_url: str) -> list[str]:
    """Tenant schemas whose alembic revision is not the installed head."""
    head = head_revision()
    return [
        schema
        for schema in tenant_schema_names(db_url)
        if current_revision(db_url, schema=schema) != head
    ]


@dataclass(frozen=True)
class TenantMigrationRun:
    """What one pass over the tenant schemas did."""

    #: Schemas brought to head.
    migrated: list[str] = field(default_factory=list)
    #: Schemas whose migration failed; their accounts are now ``suspended``.
    suspended: list[str] = field(default_factory=list)


def suspend_tenant_schema(db_url: str, schema: str) -> None:
    """Mark the account living in ``schema`` ``suspended`` — its sign-ins are refused."""
    from sqlalchemy import text

    url, table = _registry_url_and_table(db_url)
    engine = create_engine(_sync_url(url))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"UPDATE {table} SET status = 'suspended' WHERE schema_name = :schema"),  # noqa: S608 — constant table name
                {"schema": schema},
            )
    finally:
        engine.dispose()


def ensure_multi_tenant_current(db_url: str) -> TenantMigrationRun:
    """Bring the registry, then every tenant schema, to head.

    Startup of a multi-tenant instance and ``scripts/migrate_tenants.py``. No
    safety copy: that is SQLite's file backup, and a hosted database is backed
    up by its provider. The registry failing stops the run — nothing can start
    without it. A tenant schema failing suspends that one account (its members
    are refused at sign-in, the health probe lists it) and the run goes on, so
    one broken schema does not keep every other household out.
    """
    try:
        if current_revision(db_url, public=True) != head_revision(public=True):
            logger.info("Upgrading the tenant registry to head")
            upgrade_public_to_head(db_url)
    except Exception as exc:
        raise MigrationError(f"Failed to migrate the tenant registry: {exc}") from exc
    migrated: list[str] = []
    suspended: list[str] = []
    for schema in tenants_pending_migration(db_url):
        logger.info("Upgrading tenant schema %s to head", schema)
        try:
            upgrade_to_head(db_url, schema=schema)
        except Exception:
            logger.exception("Failed to migrate tenant schema %s; suspending its account", schema)
            try:
                suspend_tenant_schema(db_url, schema)
            except Exception as exc:
                raise MigrationError(
                    f"Failed to migrate tenant schema {schema} and could not suspend it: {exc}"
                ) from exc
            suspended.append(schema)
            continue
        migrated.append(schema)
    return TenantMigrationRun(migrated=migrated, suspended=suspended)
