# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a tenant's tables live, per dialect.

On PostgreSQL a tenant is a schema (``CREATE SCHEMA t_…``) and the registry is
``public``. SQLite has no schemas, but it has attached databases, and SQLAlchemy
treats an attached database's alias exactly like a schema name — so on
SQLite every schema is a file next to the main
database, attached under its schema name. Each tenant gets an engine of its
own that attaches ``public`` and that one tenant (``attach_sqlite_schemas``).
That is a development and test backend; a hosted deployment runs PostgreSQL.

Schema names are never derived from anything a user typed: ``t_`` plus twelve
hex characters from ``secrets``. Everything that splices a schema name into SQL
checks it against ``is_valid_schema_name`` first, because identifiers cannot be
bound parameters.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url

PUBLIC_SCHEMA = "public"
TENANT_SCHEMA_PREFIX = "t_"
_TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{12}$")


def new_schema_name() -> str:
    """A fresh tenant schema name: ``t_`` + 12 random hex characters."""
    return TENANT_SCHEMA_PREFIX + secrets.token_hex(6)


def is_valid_schema_name(name: str) -> bool:
    return name == PUBLIC_SCHEMA or bool(_TENANT_SCHEMA_RE.fullmatch(name))


def require_valid_schema_name(name: str) -> str:
    if not is_valid_schema_name(name):
        msg = f"Not a Kaleta schema name: {name!r}"
        raise ValueError(msg)
    return name


def quote_schema(name: str) -> str:
    """``"name"`` for SQL, after validating it — never quote an unchecked name."""
    return f'"{require_valid_schema_name(name)}"'


def is_sqlite_url(db_url: str) -> bool:
    return make_url(db_url).get_backend_name() == "sqlite"


def sqlite_schema_file(db_url: str, schema: str) -> Path:
    """The file holding ``schema`` for the SQLite database at ``db_url``."""
    require_valid_schema_name(schema)
    database = make_url(db_url).database
    if not database or database == ":memory:" or database.startswith("file:"):
        msg = "Multi-tenant SQLite needs an on-disk database file"
        raise ValueError(msg)
    main = Path(database)
    return main.with_name(f"{main.stem}.{schema}.db")


def attach_sqlite_schemas(sync_engine: Engine, db_url: str, *, tenant: str | None) -> None:
    """Attach ``public`` — and ``tenant``, if given — on every new SQLite connection.

    One tenant per engine, never all of them: SQLite looks an unqualified table
    name up in every attached database, so a connection that could see two
    tenants would let raw SQL find the wrong one's rows. Attaching only the
    tenant the engine serves makes "which tenant" a property of the connection,
    the way a schema-qualified statement makes it one on PostgreSQL.
    """
    schemas = [PUBLIC_SCHEMA] + ([tenant] if tenant is not None else [])
    files = [(schema, sqlite_schema_file(db_url, schema)) for schema in schemas]

    @event.listens_for(sync_engine, "connect")
    def _attach(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        for schema, path in files:
            # The alias is validated; the path is bound, not spliced.
            cursor.execute(f"ATTACH DATABASE ? AS {quote_schema(schema)}", (str(path),))
            cursor.execute(f"PRAGMA {quote_schema(schema)}.journal_mode=WAL")
        cursor.close()
