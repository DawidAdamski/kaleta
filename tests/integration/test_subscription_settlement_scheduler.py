# SPDX-License-Identifier: AGPL-3.0-or-later
"""Due subscription cancellations settle on a schedule, not only on page open.

One sweep settles due cancellations in every active family's schema and skips
a suspended one.

Covers: KAL-SUB-010
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.models.subscription import SubscriptionStatus
from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.services.subscription_service import SubscriptionService
from kaleta.services.subscription_settlement_scheduler import SubscriptionSettlementScheduler
from kaleta.services.tenant_service import AlembicSchemaProvisioner, TenantService
from tests.tenancy_helpers import identity, multi_tenant_database


async def _family(url: str, n: int) -> TenantContext:
    """Provision a tenant and track a Netflix 49.99 monthly subscription that,
    on 2026-04-15, was cancelled as of 2026-04-30 (so it is still active).
    """
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
            svc = SubscriptionService(session)
            sub = await svc.create(
                SubscriptionCreate(name="Netflix", amount=Decimal("49.99"), cadence_days=30)
            )
            scheduled = await svc.cancel(
                sub.id,
                effective_on=datetime.date(2026, 4, 30),
                today=datetime.date(2026, 4, 15),
            )
            assert scheduled is not None
            assert scheduled.status == SubscriptionStatus.ACTIVE
    return ctx


async def _statuses(ctx: TenantContext) -> tuple[list[str], list[str]]:
    """Return (all subscription statuses, names a reader filtering active sees)."""
    with use_tenant(ctx):
        async with AsyncSessionFactory() as session:
            svc = SubscriptionService(session)
            all_subs = await svc.list()
            active = await svc.list(status=SubscriptionStatus.ACTIVE)
    return ([s.status.value for s in all_subs], [s.name for s in active])


async def test_the_scheduler_settles_due_cancellations_in_every_active_family() -> None:
    """Covers: KAL-SUB-010

    A cancellation scheduled on 2026-04-15 as of 2026-04-30 flips Netflix to
    cancelled once the scheduler sweeps — no Subscriptions panel opened — and a
    reader filtering on active subscriptions no longer sees it. A suspended
    family is skipped, so its row stays active.
    """
    async with multi_tenant_database() as url:
        first = await _family(url, 1)
        second = await _family(url, 2)
        suspended = await _family(url, 3)
        async with AsyncSessionFactory.public() as public:
            await TenantService(public).suspend(suspended.tenant_id)

        # Today (post 2026-04-30) is past the scheduled date, so the sweep settles.
        await SubscriptionSettlementScheduler._settle_once()

        first_all, first_active = await _statuses(first)
        assert first_all == ["cancelled"]
        assert first_active == []

        second_all, second_active = await _statuses(second)
        assert second_all == ["cancelled"]
        assert second_active == []

        # The suspended family is skipped: its cancellation has not settled.
        suspended_all, suspended_active = await _statuses(suspended)
        assert suspended_all == ["active"]
        assert suspended_active == ["Netflix"]
