# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for PayeeMergeService — scoring, proposals, scan and undo."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.payee import PayeeCreate
from kaleta.schemas.payee_identity import PayeeIdentityCreate, PayeeMergeReason
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, PayeeService, TransactionService
from kaleta.services.payee_merge_service import PayeeMergeService, similarity


async def _payee(session: AsyncSession, name: str) -> int:
    return (await PayeeService(session).create(PayeeCreate(name=name))).id


async def _give_transactions(session: AsyncSession, payee_id: int, count: int) -> None:
    account = await AccountService(session).create(
        AccountCreate(name=f"Konto {payee_id}", type=AccountType.CHECKING)
    )
    category = await CategoryService(session).create(
        CategoryCreate(name=f"Kat {payee_id}", type=CategoryType.EXPENSE)
    )
    for _ in range(count):
        await TransactionService(session).create(
            TransactionCreate(
                account_id=account.id,
                category_id=category.id,
                payee_id=payee_id,
                amount=Decimal("10.00"),
                type=TransactionType.EXPENSE,
                date=datetime.date(2026, 9, 1),
                description="x",
            )
        )


class TestSimilarity:
    def test_one_edit_in_twenty_characters(self) -> None:
        assert similarity("rossmann drogeria 12", "rossmann drogeria 13") == 0.95

    def test_three_edits_in_twenty_characters(self) -> None:
        assert similarity("decathlon sport 1234", "decathlon sport 1987") == 0.85

    def test_empty_is_zero(self) -> None:
        assert similarity("", "lidl") == 0.0


class TestProposeMerges:
    async def test_seeded_dataset(self, session: AsyncSession) -> None:
        for name in (
            "Rossmann Drogeria 12",
            "Rossmann Drogeria 13",
            "Decathlon Sport 1234",
            "Decathlon Sport 1987",
            "Biedronka",
            "Zabka",
        ):
            await _payee(session, name)

        proposals = await PayeeMergeService(session).propose_merges()

        assert [(p.left_name, p.right_name, p.score, p.reason) for p in proposals] == [
            ("Rossmann Drogeria 12", "Rossmann Drogeria 13", 0.96, PayeeMergeReason.NAME),
            ("Decathlon Sport 1234", "Decathlon Sport 1987", 0.88, PayeeMergeReason.NAME),
        ]

    async def test_keeper_is_payee_with_more_transactions(self, session: AsyncSession) -> None:
        await _payee(session, "Rossmann Drogeria 12")
        busier = await _payee(session, "Rossmann Drogeria 13")
        await _give_transactions(session, busier, 2)

        [proposal] = await PayeeMergeService(session).propose_merges()

        assert (proposal.left_name, proposal.left_tx_count) == ("Rossmann Drogeria 13", 2)
        assert (proposal.right_name, proposal.right_tx_count) == ("Rossmann Drogeria 12", 0)

    async def test_identity_carries_a_pair_the_names_alone_would_not(
        self, session: AsyncSession
    ) -> None:
        svc = PayeeService(session)
        bank = await _payee(session, "PKO BANK PL")
        other = await _payee(session, "PKO BP")
        # Both normalise to "pko bp orlen"; the keys differ, so both may exist.
        await svc.add_identity(bank, PayeeIdentityCreate(pattern="PKO BP ORLEN"))
        await svc.add_identity(other, PayeeIdentityCreate(pattern="PKO BP ORLEN."))

        [proposal] = await PayeeMergeService(session).propose_merges()

        # name 1 − 5/11 → 0.5·0.5455 + identity 0.3·1.0 + merchant key 0.2·1.0
        assert (proposal.score, proposal.reason) == (0.7727, PayeeMergeReason.IDENTITY)

    async def test_pair_inside_a_detector_group_is_left_out(self, session: AsyncSession) -> None:
        a = await _payee(session, "Rossmann Drogeria 12")
        b = await _payee(session, "Rossmann Drogeria 13")
        c = await _payee(session, "Decathlon Sport 1234")
        d = await _payee(session, "Decathlon Sport 1987")

        # The two Rossmann rows are already one detector group; the Decathlon
        # pair is split across groups, so it still needs proposing.
        proposals = await PayeeMergeService(session).propose_merges(grouped=[[a, b], [c], [d]])

        assert [(p.left_name, p.right_name) for p in proposals] == [
            ("Decathlon Sport 1234", "Decathlon Sport 1987")
        ]

    async def test_dismissed_pair_is_skipped(self, session: AsyncSession) -> None:
        a = await _payee(session, "Rossmann Drogeria 12")
        b = await _payee(session, "Rossmann Drogeria 13")
        svc = PayeeMergeService(session)

        await svc.dismiss(b, a)
        await svc.dismiss(a, b)

        assert await svc.propose_merges() == []

    async def test_dismiss_validates(self, session: AsyncSession) -> None:
        a = await _payee(session, "Rossmann Drogeria 12")
        svc = PayeeMergeService(session)
        with pytest.raises(ValidationError):
            await svc.dismiss(a, a)
        with pytest.raises(NotFoundError):
            await svc.dismiss(a, 999)


class TestScan:
    async def test_threshold_outside_range_rejected(self, session: AsyncSession) -> None:
        with pytest.raises(ValidationError):
            await PayeeMergeService(session).scan(auto_merge_threshold=0.5)

    async def test_chain_folds_into_one_keeper(self, session: AsyncSession) -> None:
        for name in ("Rossmann Drogeria 12", "Rossmann Drogeria 13", "Rossmann Drogeria 14"):
            await _payee(session, name)

        result = await PayeeMergeService(session).scan(auto_merge_threshold=0.92)

        assert sorted((m.keeper_name, m.merged_name) for m in result.merged) == [
            ("Rossmann Drogeria 12", "Rossmann Drogeria 13"),
            ("Rossmann Drogeria 12", "Rossmann Drogeria 14"),
        ]
        assert result.proposals == []


class TestUndo:
    async def test_undo_refused_when_name_taken(self, session: AsyncSession) -> None:
        await _payee(session, "Rossmann Drogeria 12")
        await _payee(session, "Rossmann Drogeria 13")
        svc = PayeeMergeService(session)
        [record] = (await svc.scan(auto_merge_threshold=0.92)).merged
        await _payee(session, "Rossmann Drogeria 13")

        with pytest.raises(ConflictError):
            await svc.undo(record.id)

    async def test_undo_twice_not_found(self, session: AsyncSession) -> None:
        await _payee(session, "Rossmann Drogeria 12")
        await _payee(session, "Rossmann Drogeria 13")
        svc = PayeeMergeService(session)
        [record] = (await svc.scan(auto_merge_threshold=0.92)).merged
        await svc.undo(record.id)

        with pytest.raises(NotFoundError):
            await svc.undo(record.id)
