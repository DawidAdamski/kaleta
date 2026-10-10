# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a tenant's tables live.

A tenant is a PostgreSQL schema (``CREATE SCHEMA t_…``) and the registry is
``public`` (ADR-35).

Schema names are never derived from anything a user typed: ``t_`` plus twelve
hex characters from ``secrets``. Everything that splices a schema name into SQL
checks it against ``is_valid_schema_name`` first, because identifiers cannot be
bound parameters.
"""

from __future__ import annotations

import re
import secrets

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
