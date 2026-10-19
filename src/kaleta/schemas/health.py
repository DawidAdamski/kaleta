# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health-check response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["AuthBackendName", "HealthResponse"]

AuthBackendName = Literal["local", "supabase"]


class HealthResponse(BaseModel):
    """Probe payload with tiered disclosure (KAL-SEC-001).

    ``status`` and ``database_ok`` are the public liveness contract — every
    caller, authenticated or not, gets them. The rest are disclosed by tier and
    omitted otherwise (the route serialises with ``response_model_exclude_none``):

    - **family** (any authenticated caller): ``version``, ``auth_backend``,
      ``migrations_pending``;
    - **admin** (an instance-level credential): the above plus
      ``tenants_pending_migration``, ``keyring_sessions``, ``suspended_tenants``
      — the cross-family operational state a single family must never read.
    """

    status: str = Field(description="'ok' when the database is reachable, else 'error'")
    database_ok: bool = Field(description="True when SELECT 1 against the configured DB succeeds")
    version: str | None = Field(
        default=None,
        description="Installed Kaleta package version. Family tier and up.",
    )
    migrations_pending: bool | None = Field(
        default=None,
        description=(
            "True when the registry or any family schema is behind the installed head. "
            "Family tier and up."
        ),
    )
    tenants_pending_migration: int | None = Field(
        default=None,
        description=(
            "How many family schemas are behind the installed head — a cross-family "
            "count, so admin tier only. Null when the revisions could not be read."
        ),
    )
    auth_backend: AuthBackendName | None = Field(
        default=None,
        description="Who checks passwords: 'local' or 'supabase'. Family tier and up.",
    )
    keyring_sessions: int | None = Field(
        default=None,
        description=(
            "How many sessions hold an unlocked data key in this process — a cross-family "
            "count, so admin tier only. A count only; it drops to 0 on every restart, when "
            "each member is asked to unlock again."
        ),
    )
    suspended_tenants: list[int] | None = Field(
        default=None,
        description=(
            "Ids of suspended families — among them any whose migration failed at "
            "startup. Cross-family recon, so admin tier only. Null when the registry "
            "could not be read."
        ),
    )
