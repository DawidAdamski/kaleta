# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for `GET /api/v1/auth/mfa`.

Covers: KAL-API-005, KAL-API-006

Read-only by design: a headless install can see whether a second factor is
on, but enrolling, reissuing and turning it off all need the UI.
"""

from __future__ import annotations

import time

import pyotp
from httpx import AsyncClient

from kaleta.services.mfa_service import TOTP_INTERVAL, MfaService
from tests.conftest import make_session_factory


class TestMfaStatusOverTheApi:
    async def test_without_credentials_it_says_nothing(self, api_client_unauth: AsyncClient):
        """Covers: KAL-API-006"""
        resp = await api_client_unauth.get("/api/v1/auth/mfa")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"

    async def test_off_then_on(self, api_client: AsyncClient, api_user, db_engine):
        """Covers: KAL-API-005"""
        resp = await api_client.get("/api/v1/auth/mfa")
        assert resp.status_code == 200
        # Literals from the scenario, not from the service.
        assert resp.json() == {
            "enabled": False,
            "enabled_at": None,
            "recovery_codes_remaining": 0,
        }

        factory = make_session_factory(db_engine)
        async with factory() as session:
            mfa = MfaService(session)
            enrolment = await mfa.begin_enrolment(api_user.id)
            code = pyotp.TOTP(enrolment.secret, interval=TOTP_INTERVAL).at(int(time.time()))
            await mfa.confirm_enrolment(api_user.id, str(code))

        body = (await api_client.get("/api/v1/auth/mfa")).json()
        assert body["enabled"] is True
        assert body["enabled_at"] is not None
        assert body["recovery_codes_remaining"] == 10
        # The secret is never part of the answer, whatever else changes here.
        assert "secret" not in str(body).casefold()
