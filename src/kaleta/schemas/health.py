# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health-check response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["AuthBackendName", "HealthResponse"]

AuthBackendName = Literal["local", "supabase", "fake"]


class HealthResponse(BaseModel):
    """Unauthenticated probe payload for local monitors and uptime checks."""

    status: str = Field(description="'ok' when the database is reachable, else 'error'")
    version: str = Field(description="Installed Kaleta package version")
    database_ok: bool = Field(description="True when SELECT 1 against the configured DB succeeds")
    migrations_pending: bool = Field(
        description=("True when the registry or any family schema is behind the installed head")
    )
    tenants_pending_migration: int | None = Field(
        default=None,
        description=(
            "How many family schemas are behind the installed head. Null when the "
            "revisions could not be read."
        ),
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
            "Ids of suspended families — among them any whose migration failed at "
            "startup. Null when the registry could not be read."
        ),
    )
