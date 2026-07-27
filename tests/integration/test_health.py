# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the public health probe.

Covers: KAL-API-004
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_without_credentials(api_client_unauth: AsyncClient) -> None:
    """Covers: KAL-API-004"""
    resp = await api_client_unauth.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "0.1.0"
    assert body["database_ok"] is True
    assert body["status"] == "ok"
    assert isinstance(body["migrations_pending"], bool)
