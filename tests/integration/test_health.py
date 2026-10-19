# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the health probe's tiers.

The public (liveness) tier and the admin tier are exercised end-to-end here.
The admin tier is reached by the ``KALETA_API_TOKEN`` env token, which
``is_env_token`` resolves without any database read, so (unlike a family bearer
token) it does not hit the integration-harness asymmetry below.

The *family* tier resolves a family bearer token through the probe's own
``AsyncSessionFactory``, and the integration fixtures mint that token on a
rolled-back connection the fresh factory cannot see, so an end-to-end family
call here always resolves to ``public``. The family tier is therefore pinned at
the unit level (``tests/unit/api/test_health.py``).

Covers: KAL-API-004, KAL-SEC-001, KAL-OPS-001
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

import kaleta
from kaleta.config import settings

# A value well past ``_MIN_API_TOKEN_LENGTH`` so ``is_env_token`` accepts it.
_ENV_TOKEN = "env-token-for-the-health-probe-0123456789"

# Everything the probe discloses above the public liveness tier.
_ABOVE_PUBLIC = {
    "version",
    "auth_backend",
    "migrations_pending",
    "tenants_pending_migration",
    "keyring_sessions",
    "suspended_tenants",
}


async def test_health_without_credentials_is_liveness_only(api_client_unauth: AsyncClient) -> None:
    """An unauthenticated probe gets liveness only — no version, no cross-family state.

    This is the F-1 fix: the old route returned the whole payload (version,
    counts and the suspended-family ids) to every unauthenticated caller.

    Covers: KAL-API-004, KAL-SEC-001
    """
    resp = await api_client_unauth.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "database_ok": True}
    for field in _ABOVE_PUBLIC:
        assert field not in body, f"{field} must not be disclosed without credentials"


async def test_env_token_health_reports_a_git_derived_version(
    api_client_unauth: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admin-tier (env-token) probe carries the git-derived build version.

    The env token is an instance-level credential, so it reaches the admin tier
    and the body gains ``version``. This is the only end-to-end tier above
    public the integration harness can reach (``is_env_token`` needs no DB read).

    Covers: KAL-OPS-001, KAL-SEC-001
    """
    monkeypatch.setattr(settings, "api_token", _ENV_TOKEN)
    resp = await api_client_unauth.get(
        "/api/v1/health", headers={"Authorization": f"Bearer {_ENV_TOKEN}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    # The version the package and ``kaleta.__version__`` resolve agree with the
    # one the authenticated probe reports (KAL-OPS-001), and it is git-derived,
    # not the frozen placeholder.
    assert body["version"] == kaleta.__version__
    assert body["version"] != "0.1.0"
    assert re.match(r"^\d+\.\d+(\.\d+)?", body["version"])
    # The env token reaches the admin tier, so the cross-family state is present
    # (KAL-SEC-001): this field is exactly what a family token must never see.
    assert "suspended_tenants" in body
