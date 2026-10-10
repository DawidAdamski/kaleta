# SPDX-License-Identifier: AGPL-3.0-or-later
"""Alembic environment for the hosted tenant registry (``public``, ADR-35).

Separate from ``alembic/`` because the registry is not part of any tenant: it
is migrated once per database, before the tenant schemas, and keeps its own
version table (``alembic_version_public``) so the two histories never meet.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from kaleta.config import settings
from kaleta.db.base import PublicBase
from kaleta.models import nbp_rate as _nbp_rate  # noqa: F401 — registers public.nbp_rates
from kaleta.models import tenant as _tenant  # noqa: F401 — registers the registry tables

VERSION_TABLE = "alembic_version_public"

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = PublicBase.metadata

_effective_db_url: str = os.environ.get("KALETA_MIGRATE_URL") or settings.db_url


def run_migrations_offline() -> None:
    context.configure(
        url=_effective_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    async_engine = create_async_engine(_effective_db_url)
    async with async_engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await async_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
