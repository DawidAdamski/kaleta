# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for payee identities — creation, matching precedence and CRUD."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError
from kaleta.models.payee import Payee
from kaleta.models.payee_identity import PayeeIdentity, identity_key
from kaleta.models.subscription import Subscription, SubscriptionStatus
from kaleta.schemas.payee import PayeeCreate, PayeeUpdate
from kaleta.schemas.payee_identity import PayeeIdentityCreate, PayeeIdentityUpdate
from kaleta.services import PayeeService


@pytest.fixture
def svc(session: AsyncSession) -> PayeeService:
    return PayeeService(session)


async def _patterns(svc: PayeeService, payee_id: int) -> list[str]:
    return [i.pattern for i in await svc.list_identities(payee_id)]


class TestIdentityKey:
    def test_folds_polish_letters(self) -> None:
        assert identity_key("ŻABKA Poznań") == identity_key("żabka poznań")

    def test_collapses_whitespace(self) -> None:
        assert identity_key("  LIDL   POZNAN ") == "lidl poznan"


class TestEveryPayeeHasAnIdentity:
    async def test_created_payee_gets_its_name(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="Biedronka"))
        assert await _patterns(svc, payee.id) == ["Biedronka"]

    async def test_payee_added_directly_gets_its_name(
        self, session: AsyncSession, svc: PayeeService
    ) -> None:
        session.add(Payee(name="Seeder Payee"))
        await session.commit()
        payee = (await session.execute(select(Payee))).scalar_one()
        assert await _patterns(svc, payee.id) == ["Seeder Payee"]

    async def test_rename_adds_new_spelling_and_keeps_old(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="BIEDRONKA SP Z OO"))
        await svc.update(payee.id, PayeeUpdate(name="Biedronka"))
        assert await _patterns(svc, payee.id) == ["BIEDRONKA SP Z OO", "Biedronka"]

    async def test_deleting_payee_deletes_identities(
        self, session: AsyncSession, svc: PayeeService
    ) -> None:
        payee = await svc.create(PayeeCreate(name="Kiosk"))
        await svc.delete(payee.id)
        assert (await session.execute(select(PayeeIdentity))).scalars().all() == []


class TestMatchPrecedence:
    async def test_identity_hit_beats_name_hit(self, svc: PayeeService) -> None:
        # "Kiosk" is the *name* of one payee but an *identity* of another.
        named = await svc.create(PayeeCreate(name="Kiosk"))
        [own] = await svc.list_identities(named.id)
        await svc.update_identity(named.id, own.id, PayeeIdentityUpdate(pattern="KIOSK RUCH 7"))
        ruch = await svc.create(PayeeCreate(name="Ruch"))
        await svc.add_identity(ruch.id, PayeeIdentityCreate(pattern="Kiosk"))

        matched = await svc.match_or_create_from_name("Kiosk")

        assert matched.id == ruch.id

    async def test_name_hit_when_no_identity_matches(self, svc: PayeeService) -> None:
        named = await svc.create(PayeeCreate(name="Kiosk"))
        [own] = await svc.list_identities(named.id)
        await svc.update_identity(named.id, own.id, PayeeIdentityUpdate(pattern="KIOSK RUCH 7"))

        matched = await svc.match_or_create_from_name("Kiosk")

        assert matched.id == named.id

    async def test_exact_spelling_beats_case_insensitive_one(
        self, session: AsyncSession, svc: PayeeService
    ) -> None:
        # Two payees differing only in case, as the backfill can leave them.
        upper = await svc.create(PayeeCreate(name="LIDL"))
        lower = await svc.create(PayeeCreate(name="Lidl"))

        assert (await svc.match_or_create_from_name("Lidl")).id == lower.id
        assert (await svc.match_or_create_from_name("LIDL")).id == upper.id
        assert (await svc.match_or_create_from_name("lidl")).id == upper.id

    async def test_case_sensitive_identity_needs_exact_case(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="Apteka Gemini"))
        await svc.add_identity(payee.id, PayeeIdentityCreate(pattern="GEM", case_sensitive=True))

        assert (await svc.match_or_create_from_name("GEM")).id == payee.id
        other = await svc.match_or_create_from_name("gem")
        assert other.id != payee.id
        assert other.name == "gem"

    async def test_unknown_name_creates_payee_with_identity(self, svc: PayeeService) -> None:
        created = await svc.match_or_create_from_name("  Pasibus   Poznań ")
        assert created.name == "Pasibus Poznań"
        assert await _patterns(svc, created.id) == ["Pasibus Poznań"]


class TestIdentityCrud:
    async def test_add_duplicate_on_same_payee_conflicts(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="Lidl"))
        with pytest.raises(ConflictError):
            await svc.add_identity(payee.id, PayeeIdentityCreate(pattern="LIDL"))

    async def test_update_to_spelling_of_other_payee_conflicts(self, svc: PayeeService) -> None:
        lidl = await svc.create(PayeeCreate(name="Lidl"))
        kaufland = await svc.create(PayeeCreate(name="Kaufland"))
        [own] = await svc.list_identities(kaufland.id)
        with pytest.raises(ConflictError):
            await svc.update_identity(kaufland.id, own.id, PayeeIdentityUpdate(pattern="lidl"))
        assert await _patterns(svc, lidl.id) == ["Lidl"]

    async def test_delete_non_last_identity(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="Lidl"))
        extra = await svc.add_identity(payee.id, PayeeIdentityCreate(pattern="LIDL POZNAN"))
        await svc.delete_identity(payee.id, extra.id)
        assert await _patterns(svc, payee.id) == ["Lidl"]

    async def test_delete_last_identity_refused(self, svc: PayeeService) -> None:
        payee = await svc.create(PayeeCreate(name="Lidl"))
        [own] = await svc.list_identities(payee.id)
        with pytest.raises(ConflictError) as exc:
            await svc.delete_identity(payee.id, own.id)
        assert exc.value.code == "last_identity"

    async def test_identity_of_another_payee_not_found(self, svc: PayeeService) -> None:
        lidl = await svc.create(PayeeCreate(name="Lidl"))
        kaufland = await svc.create(PayeeCreate(name="Kaufland"))
        [own] = await svc.list_identities(lidl.id)
        with pytest.raises(NotFoundError):
            await svc.delete_identity(kaufland.id, own.id)

    async def test_list_identities_of_missing_payee(self, svc: PayeeService) -> None:
        with pytest.raises(NotFoundError):
            await svc.list_identities(999)


class TestMergeIdentities:
    async def test_merge_drops_spellings_keeper_already_has(self, svc: PayeeService) -> None:
        keeper = await svc.create(PayeeCreate(name="ORLEN"))
        other = await svc.create(PayeeCreate(name="Orlen Stacja"))
        await svc.add_identity(keeper.id, PayeeIdentityCreate(pattern="PKN ORLEN"))
        # Same spelling in different case cannot be added to two payees, so
        # plant it directly — the migration backfill can leave such pairs.
        svc.session.add(PayeeIdentity(payee_id=other.id, pattern="pkn orlen"))
        await svc.session.commit()

        await svc.merge(keeper.id, [other.id])

        # "pkn orlen" is dropped, not duplicated; order is creation order.
        assert await _patterns(svc, keeper.id) == ["ORLEN", "Orlen Stacja", "PKN ORLEN"]

    async def test_merge_rename_adds_new_name_identity(self, svc: PayeeService) -> None:
        keeper = await svc.create(PayeeCreate(name="LIDL SP. Z O.O."))
        other = await svc.create(PayeeCreate(name="Lidl 1234 Warszawa"))

        await svc.merge(keeper.id, [other.id], new_name="Lidl")

        assert await _patterns(svc, keeper.id) == [
            "LIDL SP. Z O.O.",
            "Lidl 1234 Warszawa",
            "Lidl",
        ]

    async def test_merge_moves_subscriptions_to_keeper(self, svc: PayeeService) -> None:
        keeper = await svc.create(PayeeCreate(name="Netflix"))
        other = await svc.create(PayeeCreate(name="NETFLIX.COM"))
        subscription = Subscription(
            payee_id=other.id,
            name="Netflix",
            amount=Decimal("43.00"),
            cadence_days=30,
            first_seen_at=datetime.date(2026, 1, 15),
            next_expected_at=datetime.date(2026, 10, 15),
            status=SubscriptionStatus.ACTIVE,
        )
        svc.session.add(subscription)
        await svc.session.commit()

        await svc.merge(keeper.id, [other.id])

        await svc.session.refresh(subscription)
        assert subscription.payee_id == keeper.id
