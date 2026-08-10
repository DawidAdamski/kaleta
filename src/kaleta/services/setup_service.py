# SPDX-License-Identifier: AGPL-3.0-or-later
"""First-run database setup — migrations and engine configuration."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from alembic import command
from kaleta.exceptions import MigrationError

logger = logging.getLogger(__name__)


def _alembic_ini() -> Path:
    return Path(__file__).resolve().parents[3] / "alembic.ini"


def _alembic_config() -> Config:
    return Config(str(_alembic_ini()))


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_alembic_config())


def _sync_url(db_url: str) -> str:
    """Strip async drivers so stdlib/sync SQLAlchemy can open the DB."""
    return db_url.replace("+aiosqlite", "").replace("+asyncpg", "")


def head_revision() -> str:
    """Return the alembic head revision for the installed code."""
    head = _script_directory().get_current_head()
    if head is None:
        raise MigrationError("No alembic head revision found in this installation")
    return head


def current_revision(db_url: str) -> str | None:
    """Return the DB's alembic revision, or None if unstamped / empty."""
    from alembic.runtime.migration import MigrationContext

    engine = create_engine(_sync_url(db_url))
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            return context.get_current_revision()
    finally:
        engine.dispose()


def upgrade_to_head(db_url: str) -> None:
    """Run Alembic ``upgrade head`` against ``db_url`` (synchronous)."""
    os.environ["KALETA_MIGRATE_URL"] = db_url
    try:
        command.upgrade(_alembic_config(), "head")
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
