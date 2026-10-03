# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health-check response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["AuthBackendName", "HealthResponse", "TenancyName"]

TenancyName = Literal["single", "multi"]
AuthBackendName = Literal["local", "supabase", "fake"]


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
    tenancy: TenancyName = Field(
        description="'single' (self-hosted, one household) or 'multi' (hosted, one schema each)"
    )
    auth_backend: AuthBackendName = Field(
        description="Who checks passwords: 'local', 'supabase', or the debug-only 'fake'"
    )
    keyring_sessions: int = Field(
        description=(
            "How many sessions hold an unlocked data key in this process. A count only; "
            "it drops to 0 on every restart, when each member is asked to unlock again."
        )
    )
    suspended_tenants: list[int] | None = Field(
        default=None,
        description=(
            "Multi-tenant instances only: ids of suspended accounts — among them any whose "
            "migration failed at startup. Null on a single-tenant install."
        ),
    )
