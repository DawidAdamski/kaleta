"""Personal loans — track money lent to / borrowed from other people.

The loan lives outside the bank ledger by default. Recording a repayment can
optionally mirror itself as a real Transaction on a user-picked account, so
reconciliation with the bank ledger stays a one-click opt-in.
"""

from __future__ import annotations

import builtins
import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.personal_loan import (
    Counterparty,
    LoanDirection,
    LoanStatus,
    PersonalLoan,
    PersonalLoanRepayment,
)
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.personal_loan import (
    CounterpartyCreate,
    CounterpartyUpdate,
    LoanTotals,
    PersonalLoanCreate,
    PersonalLoanUpdate,
    RepaymentCreate,
    RepaymentResponse,
)


class PersonalLoanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Counterparty CRUD ─────────────────────────────────────────────────

    async def list_counterparties(self) -> builtins.list[Counterparty]:
        result = await self.session.execute(
            select(Counterparty).order_by(Counterparty.name)
        )
        return list(result.scalars().all())

    async def get_counterparty(self, cp_id: int) -> Counterparty | None:
        result = await self.session.execute(
            select(Counterparty).where(Counterparty.id == cp_id)
        )
        return result.scalar_one_or_none()

    async def get_counterparty_by_name(self, name: str) -> Counterparty | None:
        result = await self.session.execute(
            select(Counterparty).where(Counterparty.name == name)
        )
        return result.scalar_one_or_none()

    async def upsert_counterparty(self, name: str) -> Counterparty:
        """Return an existing counterparty by name, or create one."""
        existing = await self.get_counterparty_by_name(name)
        if existing is not None:
            return existing
        cp = Counterparty(name=name)
        self.session.add(cp)
        await self.session.commit()
        await self.session.refresh(cp)
        return cp

    async def create_counterparty(
        self, payload: CounterpartyCreate
    ) -> Counterparty:
        cp = Counterparty(name=payload.name, notes=payload.notes)
        self.session.add(cp)
        await self.session.commit()
        await self.session.refresh(cp)
        return cp

    async def update_counterparty(
        self, cp_id: int, payload: CounterpartyUpdate
    ) -> Counterparty | None:
        cp = await self.get_counterparty(cp_id)
        if cp is None:
            return None
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(cp, key, value)
        await self.session.commit()
        await self.session.refresh(cp)
        return cp

    # ── Loan CRUD ─────────────────────────────────────────────────────────

    async def get_loan(self, loan_id: int) -> PersonalLoan | None:
        result = await self.session.execute(
            select(PersonalLoan)
            .options(
                selectinload(PersonalLoan.repayments),
                selectinload(PersonalLoan.counterparty),
            )
            .where(PersonalLoan.id == loan_id)
        )
        return result.scalar_one_or_none()

    async def list_loans(
        self, *, status: LoanStatus | None = None
    ) -> builtins.list[PersonalLoan]:
        stmt = (
            select(PersonalLoan)
            .options(
                selectinload(PersonalLoan.repayments),
                selectinload(PersonalLoan.counterparty),
            )
            .order_by(PersonalLoan.opened_at.desc())
        )
        if status is not None:
            stmt = stmt.where(PersonalLoan.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_loan(self, payload: PersonalLoanCreate) -> PersonalLoan:
        loan = PersonalLoan(
            counterparty_id=payload.counterparty_id,
            direction=payload.direction,
            principal=payload.principal,
            currency=payload.currency,
            opened_at=payload.opened_at,
            due_at=payload.due_at,
            notes=payload.notes,
            status=LoanStatus.OUTSTANDING,
        )
        self.session.add(loan)
        await self.session.commit()
        return await self.get_loan(loan.id)  # type: ignore[return-value]

    async def update_loan(
        self, loan_id: int, payload: PersonalLoanUpdate
    ) -> PersonalLoan | None:
        loan = await self.get_loan(loan_id)
        if loan is None:
            return None
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(loan, key, value)
        await self.session.commit()
        return await self.get_loan(loan_id)

    async def delete_loan(self, loan_id: int) -> bool:
        """Delete a loan and its repayments. Linked transactions are untouched."""
        loan = await self.get_loan(loan_id)
        if loan is None:
            return False
        await self.session.delete(loan)
        await self.session.commit()
        return True

    # ── Repayments ────────────────────────────────────────────────────────

    async def record_repayment(
        self, loan_id: int, payload: RepaymentCreate
    ) -> RepaymentResponse | None:
        """Record a repayment, optionally mirror as a real Transaction."""
        loan = await self.get_loan(loan_id)
        if loan is None:
            return None

        linked_tx_id: int | None = None
        if payload.link_account_id is not None:
            # Direction maps to Transaction.type:
            #   OUTGOING loan + repayment → cash coming back → INCOME tx.
            #   INCOMING loan + repayment → cash going out    → EXPENSE tx.
            tx_type = (
                TransactionType.INCOME
                if loan.direction == LoanDirection.OUTGOING
                else TransactionType.EXPENSE
            )
            tx = Transaction(
                account_id=payload.link_account_id,
                category_id=payload.link_category_id,
                type=tx_type,
                amount=payload.amount,
                date=payload.date,
                description=f"Personal loan repayment: {loan.counterparty.name}",
                is_internal_transfer=False,
            )
            self.session.add(tx)
            await self.session.flush()
            linked_tx_id = tx.id

        repayment = PersonalLoanRepayment(
            loan_id=loan_id,
            amount=payload.amount,
            date=payload.date,
            note=payload.note,
            linked_transaction_id=linked_tx_id,
        )
        self.session.add(repayment)

        # Auto-flip status if the remaining balance hits 0 or below.
        remaining = _compute_remaining(
            loan.principal, [r.amount for r in loan.repayments] + [payload.amount]
        )
        if remaining <= Decimal("0"):
            loan.status = LoanStatus.SETTLED
            loan.settled_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        else:
            # User may have reactivated then posted a small repayment —
            # keep status as outstanding.
            loan.status = LoanStatus.OUTSTANDING
            loan.settled_at = None

        await self.session.commit()
        await self.session.refresh(repayment)
        return RepaymentResponse.model_validate(repayment)

    async def delete_repayment(self, repayment_id: int) -> bool:
        result = await self.session.execute(
            select(PersonalLoanRepayment).where(
                PersonalLoanRepayment.id == repayment_id
            )
        )
        r = result.scalar_one_or_none()
        if r is None:
            return False
        loan_id = r.loan_id
        await self.session.delete(r)
        await self.session.commit()
        # Re-evaluate status with the remaining repayments.
        loan = await self.get_loan(loan_id)
        if loan is not None:
            remaining = _compute_remaining(
                loan.principal, [rep.amount for rep in loan.repayments]
            )
            loan.status = (
                LoanStatus.SETTLED
                if remaining <= Decimal("0") and loan.repayments
                else LoanStatus.OUTSTANDING
            )
            if loan.status == LoanStatus.OUTSTANDING:
                loan.settled_at = None
            await self.session.commit()
        return True

    # ── Totals ────────────────────────────────────────────────────────────

    async def totals(self) -> LoanTotals:
        loans = await self.list_loans()
        they_owe_you = Decimal("0.00")
        you_owe = Decimal("0.00")
        outstanding = 0
        settled = 0
        for loan in loans:
            if loan.status == LoanStatus.SETTLED:
                settled += 1
                continue
            outstanding += 1
            remaining = _compute_remaining(
                loan.principal, [r.amount for r in loan.repayments]
            )
            if remaining <= Decimal("0"):
                continue
            if loan.direction == LoanDirection.OUTGOING:
                they_owe_you += remaining
            else:
                you_owe += remaining
        return LoanTotals(
            they_owe_you=they_owe_you.quantize(Decimal("0.01")),
            you_owe=you_owe.quantize(Decimal("0.01")),
            outstanding_count=outstanding,
            settled_count=settled,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _compute_remaining(
    principal: Decimal, repayments: builtins.list[Decimal]
) -> Decimal:
    total_repaid = sum(repayments, Decimal("0"))
    return (principal - total_repaid).quantize(Decimal("0.01"))


__all__ = ["PersonalLoanService"]
