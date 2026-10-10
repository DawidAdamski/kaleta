# SPDX-License-Identifier: AGPL-3.0-or-later
"""A family schema stopped at an old revision, for tests of a data migration.

A data migration is tested the way it runs: rows written as the schema stood
before it, then ``alembic upgrade``, then a look at what came out. The schema
lives in a fresh ``<suite database>_<name>`` (``fresh_database_url``), so the
suite's own family is never at an old revision. Synchronous, because Alembic's
``env.py`` runs an event loop of its own.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from kaleta.db.tenant_schemas import new_schema_name, quote_schema
from kaleta.services.setup_service import _alembic_config, _sync_url
from tests.suite_database import fresh_database_url


@dataclass(frozen=True)
class MigrationSchema:
    url: str
    schema: str

    def upgrade(self, revision: str) -> None:
        os.environ["KALETA_MIGRATE_URL"] = self.url
        try:
            command.upgrade(_alembic_config(schema=self.schema), revision)
        finally:
            os.environ.pop("KALETA_MIGRATE_URL", None)

    def execute(
        self, sql: str, rows: list[Mapping[str, Any]] | None = None
    ) -> list[tuple[Any, ...]]:
        """Run raw ``sql`` in the schema (on ``search_path``); the rows it returns."""
        engine = create_engine(
            _sync_url(self.url), connect_args={"options": f"-csearch_path={self.schema}"}
        )
        try:
            with engine.begin() as conn:
                result = conn.execute(text(sql), rows or {})
                return [tuple(row) for row in result] if result.returns_rows else []
        finally:
            engine.dispose()

    def async_engine(self) -> AsyncEngine:
        """An engine whose ORM statements land in the schema; the caller disposes it."""
        engine = create_async_engine(self.url, poolclass=NullPool)
        return engine.execution_options(schema_translate_map={None: self.schema})


def migration_schema(name: str, revision: str) -> MigrationSchema:
    """An empty family schema in a fresh database, migrated to ``revision``."""
    url = fresh_database_url(name)
    schema = new_schema_name()
    engine = create_engine(_sync_url(url))
    try:
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {quote_schema(schema)}"))
    finally:
        engine.dispose()
    target = MigrationSchema(url=url, schema=schema)
    target.upgrade(revision)
    return target
