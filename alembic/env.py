import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from kaleta.config import settings
from kaleta.db.base import Base

# Import all models so Alembic can detect them for autogenerate.
from kaleta.models import (  # noqa: F401
    Account,
    AccountType,
    Budget,
    Category,
    CategoryType,
    Transaction,
    TransactionSplit,
    TransactionType,
)
from kaleta.models.currency_rate import CurrencyRate  # noqa: F401
from kaleta.models.institution import Institution, InstitutionType  # noqa: F401
from kaleta.models.report import SavedReport  # noqa: F401

config = context.config
if config.config_file_name is not None:
    # The app runs `alembic upgrade` in-process on startup. Left at its
    # default, fileConfig would disable every logger created before the
    # migration — i.e. the whole application — for the rest of the process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Allow programmatic migration runs to override the DB URL without restarting.
_effective_db_url: str = os.environ.get("KALETA_MIGRATE_URL") or settings.db_url

# `-x tenant_schema=t_…` migrates one tenant schema of a multi-tenant database
# (`KALETA_TENANCY=multi`, ADR-35). Unset, this is the single-tenant database
# exactly as before.
_tenant_schema: str | None = context.get_x_argument(as_dictionary=True).get("tenant_schema")
if _tenant_schema is not None:
    from kaleta.db.tenant_schemas import is_sqlite_url, require_valid_schema_name

    require_valid_schema_name(_tenant_schema)
    if is_sqlite_url(_effective_db_url):
        # A SQLite tenant schema is a standalone file, attached under its
        # schema name only at runtime. Migrating it as the main database keeps
        # batch mode's table reflection — which ignores the translate map —
        # looking at the right tables.
        from kaleta.db.tenant_schemas import sqlite_schema_file

        _effective_db_url = "sqlite+aiosqlite:///" + str(
            sqlite_schema_file(_effective_db_url, _tenant_schema)
        )
        _tenant_schema = None


def run_migrations_offline() -> None:
    context.configure(
        url=_effective_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    if _tenant_schema is not None:
        from kaleta.db.tenant_schemas import quote_schema

        if connection.dialect.name == "postgresql":
            # Raw SQL in data migrations is not touched by the translate map,
            # so it has to find the tenant's tables by search path. This is a
            # dedicated migration connection, disposed right after — the
            # pooler concern of ADR-35 is about request connections.
            connection.exec_driver_sql(f"SET search_path TO {quote_schema(_tenant_schema)}")
            connection.commit()
        connection = connection.execution_options(schema_translate_map={None: _tenant_schema})
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # required for SQLite ALTER TABLE support
        version_table_schema=_tenant_schema,
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
