# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration tests for API authentication."""

from __future__ import annotations

from httpx import AsyncClient


class TestApiAuth:
    async def test_unauthenticated_returns_401_json(self, api_client_unauth: AsyncClient):
        """Covers: KAL-AUTH-005"""
        resp = await api_client_unauth.get("/api/v1/accounts/")
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "unauthorized"

    async def test_bearer_token_returns_200(self, api_client: AsyncClient):
        """Covers: KAL-AUTH-006"""
        resp = await api_client.get("/api/v1/accounts/")
        assert resp.status_code == 200
        assert resp.json() == []
