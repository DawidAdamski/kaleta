# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the public health probe.

Covers: KAL-API-004
"""

from __future__ import annotations

from httpx import AsyncClient

import kaleta


async def test_health_without_credentials(api_client_unauth: AsyncClient) -> None:
    """Covers: KAL-API-004, KAL-OPS-001"""
    resp = await api_client_unauth.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    # The version is git-derived (auto-versioning), not the old hard-coded 0.1.0;
    # it matches the package version the app resolves at import.
    assert body["version"] == kaleta.__version__
    assert body["version"] != "0.1.0"
    assert body["version"]
    assert body["database_ok"] is True
    assert body["status"] == "ok"
    assert isinstance(body["migrations_pending"], bool)
