# SPDX-License-Identifier: AGPL-3.0-or-later
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from kaleta.config import settings


class Base(DeclarativeBase):
    """Every table of one household: the SQLite file, or one tenant schema."""


class PublicBase(DeclarativeBase):
    """The cross-tenant registry (``public.tenants`` and friends, ADR-35).

    Its own ``MetaData`` on purpose: ``Base.metadata`` is what a tenant schema
    is built from (``create_all`` in tests, autogenerate in ``alembic/``), and
    the registry must never appear inside a tenant. Migrated by
    ``alembic_public/``.
    """

    metadata = MetaData()


def create_engine() -> AsyncEngine:
    connect_args = {"check_same_thread": False} if "sqlite" in settings.db_url else {}
    return create_async_engine(
        settings.db_url,
        echo=settings.debug,
        connect_args=connect_args,
    )


engine: AsyncEngine = create_engine()
