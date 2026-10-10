# SPDX-License-Identifier: AGPL-3.0-or-later
"""The retention purge on the registry layout: one sweep, every active family.

Covers: KAL-OBS-004
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.models.app_event import AppEvent
from kaleta.services.event_retention_scheduler import EventRetentionScheduler
from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService
from tests.tenancy_helpers import identity, multi_tenant_database


def _event(event_id: str, *, age_days: int) -> AppEvent:
    return AppEvent(
        event_id=event_id,
        occurred_at=datetime.now(UTC) - timedelta(days=age_days),
        level="ERROR",
        route="/",
        exception_class="RuntimeError",
        stack_hash="abc",
        stack_trace="(none)",
        app_version="test",
    )


async def _family(url: str, n: int) -> TenantContext:
    async with AsyncSessionFactory.public() as public:
        service = TenantService(
            public, provisioner=AlembicSchemaProvisioner(url, AsyncSessionFactory.public)
        )
        await service.provision(identity(n))
        membership = await service.get_member_by_subject(identity(n).subject)
    assert membership is not None
    ctx = membership.context()
    with use_tenant(ctx):
        async with AsyncSessionFactory() as session:
            session.add_all([_event(f"OLD{n}", age_days=30), _event(f"NEW{n}", age_days=0)])
            await session.commit()
    return ctx


async def _event_ids(ctx: TenantContext) -> list[str]:
    with use_tenant(ctx):
        async with AsyncSessionFactory() as session:
            rows = await session.execute(select(AppEvent.event_id).order_by(AppEvent.event_id))
            return list(rows.scalars())


@pytest.mark.asyncio
async def test_the_purge_visits_every_active_family_and_skips_a_suspended_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Covers: KAL-OBS-004"""
    monkeypatch.setattr(settings, "events_enabled", True)
    monkeypatch.setattr(settings, "event_retention_days", 7)
    async with multi_tenant_database() as url:
        first = await _family(url, 1)
        second = await _family(url, 2)
        suspended = await _family(url, 3)
        async with AsyncSessionFactory.public() as public:
            await TenantService(public).suspend(suspended.tenant_id)

        await EventRetentionScheduler._purge_once()

        assert await _event_ids(first) == ["NEW1"]
        assert await _event_ids(second) == ["NEW2"]
        assert await _event_ids(suspended) == ["NEW3", "OLD3"]
