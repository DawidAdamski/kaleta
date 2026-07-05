"""First-run database setup — migrations and engine configuration."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


async def run_migrations(db_url: str) -> None:
    """Run Alembic migrations in a thread-pool executor (synchronous Alembic API)."""
    from alembic.config import Config

    from alembic import command

    alembic_ini = Path(__file__).resolve().parents[3] / "alembic.ini"

    def _upgrade() -> None:
        os.environ["KALETA_MIGRATE_URL"] = db_url
        try:
            cfg = Config(str(alembic_ini))
            command.upgrade(cfg, "head")
        finally:
            os.environ.pop("KALETA_MIGRATE_URL", None)

    await asyncio.get_event_loop().run_in_executor(None, _upgrade)


async def activate_database(db_url: str, *, name: str) -> None:
    """Run migrations, configure the engine, and persist the chosen database."""
    from kaleta.config import settings
    from kaleta.config.setup_config import save_db
    from kaleta.db import configure_database

    await run_migrations(db_url)
    configure_database(db_url, debug=settings.debug)
    save_db(db_url, name=name)
