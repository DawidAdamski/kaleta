# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health-check response schema."""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["HealthResponse"]


class HealthResponse(BaseModel):
    """Unauthenticated probe payload for local monitors and uptime checks."""

    status: str = Field(description="'ok' when the database is reachable, else 'error'")
    version: str = Field(description="Installed Kaleta package version")
    database_ok: bool = Field(description="True when SELECT 1 against the configured DB succeeds")
    migrations_pending: bool = Field(
        description="True when the DB alembic revision differs from the installed head"
    )
    tenants_pending_migration: int | None = Field(
        default=None,
        description=(
            "Multi-tenant instances only: how many tenant schemas are behind the installed "
            "head. Null on a single-tenant install."
        ),
    )
