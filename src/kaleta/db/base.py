# SPDX-License-Identifier: AGPL-3.0-or-later
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Every table of one household: one tenant schema (ADR-35)."""


class PublicBase(DeclarativeBase):
    """The cross-tenant registry (``public.tenants`` and friends, ADR-35).

    Its own ``MetaData`` on purpose: ``Base.metadata`` is what a tenant schema
    is built from (``create_all`` in tests, autogenerate in ``alembic/``), and
    the registry must never appear inside a tenant. Migrated by
    ``alembic_public/``.
    """

    metadata = MetaData()
