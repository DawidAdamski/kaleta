# SPDX-License-Identifier: AGPL-3.0-or-later
"""Personal loans — track money lent to / borrowed from other people.

The loan lives outside the bank ledger by default. Recording a repayment can
optionally mirror itself as a real Transaction on a user-picked account, so
reconciliation with the bank ledger stays a one-click opt-in.
"""

from __future__ import annotations

import builtins
import datetime
from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.account import Account
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
    LoanLinkCandidate,
    LoanTotals,
    PersonalLoanCreate,
    PersonalLoanUpdate,
    RepaymentCreate,
    RepaymentResponse,
)
from kaleta.services.loan_links import loan_linked_transaction_ids


class PersonalLoanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Counterparty CRUD ─────────────────────────────────────────────────

    async def list_counterparties(self) -> builtins.list[Counterparty]:
        result = await self.session.execute(select(Counterparty).order_by(Counterparty.name))
        return list(result.scalars().all())

    async def get_counterparty(self, cp_id: int) -> Counterparty | None:
        result = await self.session.execute(select(Counterparty).where(Counterparty.id == cp_id))
        return result.scalar_one_or_none()

    async def get_counterparty_by_name(self, name: str) -> Counterparty | None:
        result = await self.session.execute(select(Counterparty).where(Counterparty.name == name))
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

    async def create_counterparty(self, payload: CounterpartyCreate) -> Counterparty:
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

    async def list_loans(self, *, status: LoanStatus | None = None) -> builtins.list[PersonalLoan]:
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
        if payload.transaction_id is not None:
            await self._check_linkable(payload.transaction_id)
        loan = PersonalLoan(
            counterparty_id=payload.counterparty_id,
            direction=payload.direction,
            principal=payload.principal,
            currency=payload.currency,
            opened_at=payload.opened_at,
            due_at=payload.due_at,
            notes=payload.notes,
            status=LoanStatus.OUTSTANDING,
            transaction_id=payload.transaction_id,
        )
        self.session.add(loan)
        await self._commit_link(payload.transaction_id)
        return await self.get_loan(loan.id)  # type: ignore[return-value]

    async def update_loan(self, loan_id: int, payload: PersonalLoanUpdate) -> PersonalLoan | None:
        loan = await self.get_loan(loan_id)
        if loan is None:
            return None
        changes = payload.model_dump(exclude_unset=True)
        tx_id = changes.get("transaction_id")
        if tx_id is not None and tx_id != loan.transaction_id:
            await self._check_linkable(tx_id)
        for key, value in changes.items():
            setattr(loan, key, value)
        await self._commit_link(tx_id)
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

        if payload.link_transaction_id is not None and payload.link_account_id is not None:
            raise ValidationError(
                "Link an existing transaction or mirror to an account, not both",
                code="repayment_link_ambiguous",
            )

        linked_tx_id: int | None = None
        if payload.link_transaction_id is not None:
            await self._check_linkable(payload.link_transaction_id)
            linked_tx_id = payload.link_transaction_id
        elif payload.link_account_id is not None:
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
        remaining = compute_remaining(
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
            select(PersonalLoanRepayment).where(PersonalLoanRepayment.id == repayment_id)
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
            remaining = compute_remaining(loan.principal, [rep.amount for rep in loan.repayments])
            loan.status = (
                LoanStatus.SETTLED
                if remaining <= Decimal("0") and loan.repayments
                else LoanStatus.OUTSTANDING
            )
            if loan.status == LoanStatus.OUTSTANDING:
                loan.settled_at = None
            await self.session.commit()
        return True

    # ── Ledger links ──────────────────────────────────────────────────────

    async def list_link_candidates(
        self,
        *,
        limit: int = 200,
        include_ids: Collection[int] = (),
    ) -> builtins.list[LoanLinkCandidate]:
        """Recent transactions a loan or repayment may link, newest first.

        Internal transfers (money between the user's own accounts) and
        transactions already linked to a loan are left out, except those in
        ``include_ids`` — the current links, so an edit can keep them.
        """
        base = (
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.description,
                Account.name.label("account_name"),
            )
            .join(Account, Transaction.account_id == Account.id)
            .order_by(Transaction.date.desc(), Transaction.id.desc())
        )
        recent = await self.session.execute(
            base.where(
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.id.not_in(loan_linked_transaction_ids()),
            ).limit(limit)
        )
        rows = list(recent.all())
        if include_ids:
            # Current links are always offered, however old they are.
            current = await self.session.execute(base.where(Transaction.id.in_(include_ids)))
            seen = {row.id for row in rows}
            rows.extend(row for row in current.all() if row.id not in seen)
            rows.sort(key=lambda row: (row.date, row.id), reverse=True)
        return [
            LoanLinkCandidate(
                id=row.id,
                date=row.date,
                amount=Decimal(str(row.amount)),
                description=row.description,
                account_name=row.account_name,
            )
            for row in rows
        ]

    async def _commit_link(self, transaction_id: int | None) -> None:
        """Commit; a concurrent link of the same transaction becomes a ``ConflictError``.

        ``_check_linkable`` runs before the write, so two requests can both pass
        it — ``uq_personal_loans_transaction_id`` then rejects the second.
        """
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if transaction_id is None:
                raise
            raise ConflictError(
                f"Transaction {transaction_id} is already linked to a loan",
                code="loan_transaction_taken",
            ) from exc

    async def _check_linkable(self, transaction_id: int) -> None:
        """Raise unless ``transaction_id`` exists and no loan or repayment links it."""
        tx = await self.session.get(Transaction, transaction_id)
        if tx is None:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        linked = loan_linked_transaction_ids().subquery()
        taken = await self.session.execute(select(linked.c.id).where(linked.c.id == transaction_id))
        if taken.first() is not None:
            raise ConflictError(
                f"Transaction {transaction_id} is already linked to a loan",
                code="loan_transaction_taken",
            )

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
            remaining = compute_remaining(loan.principal, [r.amount for r in loan.repayments])
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


class PersonalLoanFormError(Exception):
    """Raised when personal-loan dialog fields fail validation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def compute_remaining(principal: Decimal, repayments: builtins.list[Decimal]) -> Decimal:
    total_repaid = sum(repayments, Decimal("0"))
    return (principal - total_repaid).quantize(Decimal("0.01"))


def parse_loan_form(
    *,
    counterparty: str,
    direction_value: str,
    principal_value: object,
    currency_value: str,
    opened_value: str,
    due_value: str,
    notes_value: str,
) -> tuple[str, LoanDirection, Decimal, str, datetime.date, datetime.date | None, str | None]:
    """Parse loan dialog fields into validated create/update payload parts."""
    cp_name = (counterparty or "").strip()
    if not cp_name:
        raise PersonalLoanFormError("Counterparty required")
    try:
        principal = Decimal(str(principal_value or 0))
        if principal <= 0:
            raise PersonalLoanFormError("Amount must be > 0")
        opened_at = datetime.date.fromisoformat(opened_value or datetime.date.today().isoformat())
        due_at = datetime.date.fromisoformat(due_value) if due_value else None
        currency = (currency_value or "PLN").strip().upper()[:3] or "PLN"
        direction = LoanDirection(direction_value)
        notes = (notes_value or "").strip() or None
    except (ValueError, TypeError) as exc:
        raise PersonalLoanFormError(str(exc)) from exc
    return cp_name, direction, principal, currency, opened_at, due_at, notes


def parse_repayment_form(
    *,
    amount_value: object,
    date_value: str,
    link_account_value: object | None,
    link_category_value: object | None,
    note_value: str,
    link_transaction_value: object | None = None,
) -> RepaymentCreate:
    """Parse repayment dialog fields into a ``RepaymentCreate`` payload."""
    try:
        amount = Decimal(str(amount_value or 0))
        if amount <= 0:
            raise PersonalLoanFormError("Amount must be > 0")
        rep_date = datetime.date.fromisoformat(date_value or datetime.date.today().isoformat())
        link_acc_raw = link_account_value
        link_acc = (
            int(str(link_acc_raw))
            if link_acc_raw is not None and int(str(link_acc_raw)) != 0
            else None
        )
        link_cat = int(str(link_category_value)) if link_category_value is not None else None
        link_tx = (
            int(str(link_transaction_value)) if link_transaction_value not in (None, "") else None
        )
        note = (note_value or "").strip() or None
    except (ValueError, TypeError) as exc:
        raise PersonalLoanFormError(str(exc)) from exc
    if link_tx is not None and link_acc is not None:
        raise PersonalLoanFormError(
            "Link an existing transaction or mirror to an account, not both"
        )
    return RepaymentCreate(
        amount=amount,
        date=rep_date,
        note=note,
        link_account_id=link_acc,
        link_category_id=link_cat,
        link_transaction_id=link_tx,
    )


__all__ = [
    "PersonalLoanFormError",
    "PersonalLoanService",
    "compute_remaining",
    "parse_loan_form",
    "parse_repayment_form",
]
