"""Unit tests for PersonalLoanService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.personal_loan import (
    LoanDirection,
    LoanStatus,
    PersonalLoan,
    PersonalLoanRepayment,
)
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.personal_loan import (
    CounterpartyCreate,
    PersonalLoanCreate,
    RepaymentCreate,
)
from kaleta.services import AccountService, PersonalLoanService


async def _make_counterparty(session: AsyncSession, name: str) -> int:
    svc = PersonalLoanService(session)
    cp = await svc.create_counterparty(CounterpartyCreate(name=name))
    return cp.id


async def _make_loan(
    session: AsyncSession,
    *,
    counterparty_id: int,
    direction: LoanDirection = LoanDirection.OUTGOING,
    principal: Decimal = Decimal("1000"),
    opened_at: datetime.date = datetime.date(2026, 4, 1),
    due_at: datetime.date | None = None,
) -> int:
    loan = await PersonalLoanService(session).create_loan(
        PersonalLoanCreate(
            counterparty_id=counterparty_id,
            direction=direction,
            principal=principal,
            opened_at=opened_at,
            due_at=due_at,
        )
    )
    return loan.id


# ── Counterparty ─────────────────────────────────────────────────────────────


class TestCounterparty:
    async def test_upsert_returns_existing(self, session: AsyncSession):
        svc = PersonalLoanService(session)
        a = await svc.upsert_counterparty("Marek")
        b = await svc.upsert_counterparty("Marek")
        assert a.id == b.id

    async def test_upsert_creates_new(self, session: AsyncSession):
        svc = PersonalLoanService(session)
        await svc.upsert_counterparty("Alice")
        await svc.upsert_counterparty("Bob")
        cps = await svc.list_counterparties()
        names = {c.name for c in cps}
        assert names == {"Alice", "Bob"}


# ── Loan CRUD ────────────────────────────────────────────────────────────────


class TestLoanCrud:
    async def test_create_persists_outstanding(self, session: AsyncSession):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(session, counterparty_id=cp)
        loan = await PersonalLoanService(session).get_loan(loan_id)
        assert loan is not None
        assert loan.status == LoanStatus.OUTSTANDING
        assert loan.principal == Decimal("1000")

    async def test_delete_cascades_repayments(self, session: AsyncSession):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(session, counterparty_id=cp)
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("100"),
                date=datetime.date(2026, 4, 15),
            ),
        )
        assert await svc.delete_loan(loan_id) is True
        remaining_reps = (
            await session.execute(
                select(PersonalLoanRepayment).where(
                    PersonalLoanRepayment.loan_id == loan_id
                )
            )
        ).scalars().all()
        assert remaining_reps == []

    async def test_delete_keeps_linked_transactions(
        self, session: AsyncSession
    ):
        cp = await _make_counterparty(session, "Marek")
        # Account for the optional linked transaction.
        acc = await AccountService(session).create(
            AccountCreate(
                name="Main", type=AccountType.CHECKING, balance=Decimal("0")
            )
        )
        loan_id = await _make_loan(session, counterparty_id=cp)
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("100"),
                date=datetime.date(2026, 4, 15),
                link_account_id=acc.id,
            ),
        )
        # Transaction was created.
        tx_count_before = (
            (await session.execute(select(Transaction))).scalars().all()
        )
        assert len(tx_count_before) == 1
        linked_tx = tx_count_before[0]
        await svc.delete_loan(loan_id)
        # Loan gone.
        assert (
            await session.execute(select(PersonalLoan).where(PersonalLoan.id == loan_id))
        ).scalar_one_or_none() is None
        # Transaction still present — only the FK was cleared via SET NULL.
        tx_after = (await session.execute(select(Transaction))).scalars().all()
        assert len(tx_after) == 1
        assert tx_after[0].id == linked_tx.id


# ── Repayments flip status ───────────────────────────────────────────────────


class TestRepayments:
    async def test_partial_repayment_keeps_outstanding(
        self, session: AsyncSession
    ):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(
            session, counterparty_id=cp, principal=Decimal("500")
        )
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("100"),
                date=datetime.date(2026, 4, 15),
            ),
        )
        loan = await svc.get_loan(loan_id)
        assert loan is not None
        assert loan.status == LoanStatus.OUTSTANDING
        assert loan.settled_at is None

    async def test_full_repayment_settles(self, session: AsyncSession):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(
            session, counterparty_id=cp, principal=Decimal("500")
        )
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("300"),
                date=datetime.date(2026, 4, 10),
            ),
        )
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("200"),
                date=datetime.date(2026, 4, 20),
            ),
        )
        loan = await svc.get_loan(loan_id)
        assert loan is not None
        assert loan.status == LoanStatus.SETTLED
        assert loan.settled_at is not None

    async def test_delete_repayment_unsettles(self, session: AsyncSession):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(
            session, counterparty_id=cp, principal=Decimal("500")
        )
        svc = PersonalLoanService(session)
        rep = await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("500"), date=datetime.date(2026, 4, 10)
            ),
        )
        assert rep is not None
        assert (await svc.get_loan(loan_id)).status == LoanStatus.SETTLED  # type: ignore[union-attr]
        # Remove the repayment → loan should re-open.
        assert await svc.delete_repayment(rep.id) is True
        loan = await svc.get_loan(loan_id)
        assert loan is not None
        assert loan.status == LoanStatus.OUTSTANDING

    async def test_linked_transaction_created_with_correct_type(
        self, session: AsyncSession
    ):
        cp = await _make_counterparty(session, "Marek")
        acc = await AccountService(session).create(
            AccountCreate(
                name="Main", type=AccountType.CHECKING, balance=Decimal("0")
            )
        )
        # OUTGOING loan (they owe me) + repayment → INCOME tx.
        out_loan = await _make_loan(
            session, counterparty_id=cp, direction=LoanDirection.OUTGOING
        )
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            out_loan,
            RepaymentCreate(
                amount=Decimal("50"),
                date=datetime.date(2026, 4, 10),
                link_account_id=acc.id,
            ),
        )
        # INCOMING loan (I owe them) + repayment → EXPENSE tx.
        cp2 = await _make_counterparty(session, "Alice")
        in_loan = await _make_loan(
            session, counterparty_id=cp2, direction=LoanDirection.INCOMING
        )
        await svc.record_repayment(
            in_loan,
            RepaymentCreate(
                amount=Decimal("25"),
                date=datetime.date(2026, 4, 11),
                link_account_id=acc.id,
            ),
        )
        txs = (await session.execute(select(Transaction))).scalars().all()
        types = {t.amount: t.type for t in txs}
        assert types[Decimal("50.00")] == TransactionType.INCOME
        assert types[Decimal("25.00")] == TransactionType.EXPENSE


# ── Totals ───────────────────────────────────────────────────────────────────


class TestTotals:
    async def test_totals_split_by_direction(self, session: AsyncSession):
        cp1 = await _make_counterparty(session, "Marek")
        cp2 = await _make_counterparty(session, "Alice")
        await _make_loan(
            session,
            counterparty_id=cp1,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("300"),
        )
        await _make_loan(
            session,
            counterparty_id=cp2,
            direction=LoanDirection.INCOMING,
            principal=Decimal("500"),
        )
        t = await PersonalLoanService(session).totals()
        assert t.they_owe_you == Decimal("300.00")
        assert t.you_owe == Decimal("500.00")
        assert t.outstanding_count == 2
        assert t.settled_count == 0

    async def test_totals_exclude_settled(self, session: AsyncSession):
        cp = await _make_counterparty(session, "Marek")
        loan_id = await _make_loan(
            session,
            counterparty_id=cp,
            direction=LoanDirection.OUTGOING,
            principal=Decimal("200"),
        )
        svc = PersonalLoanService(session)
        await svc.record_repayment(
            loan_id,
            RepaymentCreate(
                amount=Decimal("200"), date=datetime.date(2026, 4, 15)
            ),
        )
        t = await svc.totals()
        assert t.they_owe_you == Decimal("0.00")
        assert t.settled_count == 1
        assert t.outstanding_count == 0
