# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wizard projections — the budget builder normalises like the panel."""

from __future__ import annotations

from decimal import Decimal

from kaleta.schemas.subscription import SubscriptionCreate
from kaleta.services import SubscriptionService, WizardProjectionService
from tests.conftest import make_session_factory


async def test_budget_builder_projects_a_subscription_like_the_panel(db_engine) -> None:
    """Covers: KAL-SUB-009

    A yearly Domain 120.00 bill projects to 10.00 a month in the budget
    builder — the same twelfth the Subscriptions panel shows (KAL-SUB-002),
    not the old 30-day approximation (120 x 30 / 365 = 9.86).
    """
    async with make_session_factory(db_engine)() as session:
        await SubscriptionService(session).create(
            SubscriptionCreate(name="Domain", amount=Decimal("120.00"), cadence_days=365)
        )
        result = await WizardProjectionService(session).get_budget_builder_sources(2026)

    [row] = result.fixed
    assert row.source_kind == "subscription"
    assert row.amount == Decimal("10.00")
    assert row.cadence == "yearly"
