# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/api/v1/personal-loans`` — money lent to or borrowed from people, and its repayments."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import NotFoundError
from kaleta.models.personal_loan import Counterparty, LoanStatus, PersonalLoan
from kaleta.schemas.personal_loan import (
    CounterpartyCreate,
    CounterpartyResponse,
    CounterpartyUpdate,
    LoanLinkCandidate,
    LoanTotals,
    PersonalLoanCreate,
    PersonalLoanUpdate,
    PersonalLoanWithRepayments,
    RepaymentCreate,
    RepaymentResponse,
)
from kaleta.services.personal_loan_service import PersonalLoanService, compute_remaining

_LOAN_404: dict[int | str, dict[str, Any]] = {404: {"description": "Loan not found"}}
_CP_404: dict[int | str, dict[str, Any]] = {404: {"description": "Counterparty not found"}}
_CP_409: dict[int | str, dict[str, Any]] = {
    409: {"description": "Another counterparty has that name"}
}
_LOAN_422: dict[int | str, dict[str, Any]] = {
    422: {"description": "An unknown counterparty, or a required field set to null"}
}
_LINK_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "The linked transaction does not exist"},
    409: {"description": "The transaction is already linked to a loan or repayment"},
}

router = APIRouter(prefix="/personal-loans", tags=["Personal loans"])


def _loan_out(loan: PersonalLoan) -> PersonalLoanWithRepayments:
    amounts = [r.amount for r in loan.repayments]
    return PersonalLoanWithRepayments(
        id=loan.id,
        counterparty_id=loan.counterparty_id,
        counterparty_name=loan.counterparty.name,
        direction=loan.direction,
        principal=loan.principal,
        currency=loan.currency,
        opened_at=loan.opened_at,
        due_at=loan.due_at,
        notes=loan.notes,
        transaction_id=loan.transaction_id,
        status=loan.status,
        settled_at=loan.settled_at,
        repayments=[RepaymentResponse.model_validate(r) for r in loan.repayments],
        repaid_total=sum(amounts, Decimal("0")).quantize(Decimal("0.01")),
        remaining=compute_remaining(loan.principal, amounts),
    )


def _loan_or_404(loan: PersonalLoan | None, loan_id: int) -> PersonalLoanWithRepayments:
    if loan is None:
        raise NotFoundError(f"Loan {loan_id} not found")
    return _loan_out(loan)


def _cp_or_404(cp: Counterparty | None, cp_id: int) -> CounterpartyResponse:
    if cp is None:
        raise NotFoundError(f"Counterparty {cp_id} not found")
    return CounterpartyResponse.model_validate(cp)


# ── Counterparties ────────────────────────────────────────────────────────────


@router.get(
    "/counterparties",
    response_model=list[CounterpartyResponse],
    summary="List counterparties",
    description="The people loans are made with, by name.",
)
async def list_counterparties(
    session: AsyncSession = Depends(get_session),
) -> list[CounterpartyResponse]:
    people = await PersonalLoanService(session).list_counterparties()
    return [CounterpartyResponse.model_validate(cp) for cp in people]


@router.post(
    "/counterparties",
    response_model=CounterpartyResponse,
    status_code=201,
    summary="Create a counterparty",
    responses=_CP_409,
)
async def create_counterparty(
    data: CounterpartyCreate, session: AsyncSession = Depends(get_session)
) -> CounterpartyResponse:
    cp = await PersonalLoanService(session).create_counterparty(data)
    return CounterpartyResponse.model_validate(cp)


@router.get(
    "/counterparties/{cp_id}",
    response_model=CounterpartyResponse,
    summary="Get a counterparty",
    responses=_CP_404,
)
async def get_counterparty(
    cp_id: int, session: AsyncSession = Depends(get_session)
) -> CounterpartyResponse:
    return _cp_or_404(await PersonalLoanService(session).get_counterparty(cp_id), cp_id)


@router.put(
    "/counterparties/{cp_id}",
    response_model=CounterpartyResponse,
    summary="Update a counterparty",
    description="Partially updates the counterparty. Only fields in the body change.",
    responses={**_CP_404, **_CP_409, 422: {"description": "A null name"}},
)
async def update_counterparty(
    cp_id: int, data: CounterpartyUpdate, session: AsyncSession = Depends(get_session)
) -> CounterpartyResponse:
    cp = await PersonalLoanService(session).update_counterparty(cp_id, data)
    return _cp_or_404(cp, cp_id)


# ── Read-only helpers ─────────────────────────────────────────────────────────


@router.get(
    "/totals",
    response_model=LoanTotals,
    summary="Personal loan totals",
    description=(
        "What outstanding loans still come to, by direction: `they_owe_you` for money "
        "lent, `you_owe` for money borrowed; plus how many loans are open and settled."
    ),
)
async def loan_totals(session: AsyncSession = Depends(get_session)) -> LoanTotals:
    return await PersonalLoanService(session).totals()


@router.get(
    "/link-candidates",
    response_model=list[LoanLinkCandidate],
    summary="Transactions a loan or repayment can link to",
    description=(
        "Recent transactions, newest first, that are not internal transfers and not "
        "already linked to a loan or a repayment."
    ),
)
async def link_candidates(
    limit: int = Query(200, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[LoanLinkCandidate]:
    return await PersonalLoanService(session).list_link_candidates(limit=limit)


# ── Loans ─────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[PersonalLoanWithRepayments],
    summary="List personal loans",
    description="Every loan, newest first, with its repayments and what is left to repay.",
)
async def list_personal_loans(
    status: LoanStatus | None = Query(None, description="Only outstanding or settled loans"),
    session: AsyncSession = Depends(get_session),
) -> list[PersonalLoanWithRepayments]:
    loans = await PersonalLoanService(session).list_loans(status=status)
    return [_loan_out(loan) for loan in loans]


@router.post(
    "/",
    response_model=PersonalLoanWithRepayments,
    status_code=201,
    summary="Create a personal loan",
    description=(
        "Records money lent (`outgoing`) or borrowed (`incoming`). `transaction_id` "
        "links the ledger transaction that moved the principal."
    ),
    responses={**_LOAN_422, **_LINK_ERRORS},
)
async def create_personal_loan(
    data: PersonalLoanCreate, session: AsyncSession = Depends(get_session)
) -> PersonalLoanWithRepayments:
    service = PersonalLoanService(session)
    loan = await service.create_loan(data)
    return _loan_out(loan)


@router.get(
    "/{loan_id}",
    response_model=PersonalLoanWithRepayments,
    summary="Get a personal loan",
    responses=_LOAN_404,
)
async def get_personal_loan(
    loan_id: int, session: AsyncSession = Depends(get_session)
) -> PersonalLoanWithRepayments:
    return _loan_or_404(await PersonalLoanService(session).get_loan(loan_id), loan_id)


@router.put(
    "/{loan_id}",
    response_model=PersonalLoanWithRepayments,
    summary="Update a personal loan",
    description=(
        "Partially updates the loan. `transaction_id: null` unlinks the principal; "
        "`status: settled` closes the loan by hand and stamps `settled_at`, "
        "`outstanding` reopens it."
    ),
    responses={**_LOAN_404, **_LOAN_422, 409: _LINK_ERRORS[409]},
)
async def update_personal_loan(
    loan_id: int, data: PersonalLoanUpdate, session: AsyncSession = Depends(get_session)
) -> PersonalLoanWithRepayments:
    return _loan_or_404(await PersonalLoanService(session).update_loan(loan_id, data), loan_id)


@router.delete(
    "/{loan_id}",
    status_code=204,
    summary="Delete a personal loan",
    description="Deletes the loan and its repayments. Linked transactions stay in the ledger.",
    responses=_LOAN_404,
)
async def delete_personal_loan(loan_id: int, session: AsyncSession = Depends(get_session)) -> None:
    if not await PersonalLoanService(session).delete_loan(loan_id):
        raise NotFoundError(f"Loan {loan_id} not found")


# ── Repayments ────────────────────────────────────────────────────────────────


@router.post(
    "/{loan_id}/repayments",
    response_model=RepaymentResponse,
    status_code=201,
    summary="Record a repayment",
    description=(
        "Records a repayment, and settles the loan once nothing is left (an overpaid "
        "loan has a negative `remaining`). `link_transaction_id` points at an existing "
        "transaction; `link_account_id` (with optional `link_category_id`) instead "
        "mirrors the repayment as a new income (money lent) or expense (money borrowed)."
    ),
    responses={
        404: {"description": "Loan or linked transaction not found"},
        409: _LINK_ERRORS[409],
        422: {
            "description": (
                "Both link_transaction_id and link_account_id, or an unknown account or category"
            )
        },
    },
)
async def record_repayment(
    loan_id: int, data: RepaymentCreate, session: AsyncSession = Depends(get_session)
) -> RepaymentResponse:
    repayment = await PersonalLoanService(session).record_repayment(loan_id, data)
    if repayment is None:
        raise NotFoundError(f"Loan {loan_id} not found")
    return repayment


@router.delete(
    "/{loan_id}/repayments/{repayment_id}",
    status_code=204,
    summary="Delete a repayment",
    description=(
        "Deletes the repayment and re-evaluates the loan's status. A linked or mirrored "
        "transaction stays in the ledger."
    ),
    responses={404: {"description": "No such repayment on this loan"}},
)
async def delete_repayment(
    loan_id: int, repayment_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    if not await PersonalLoanService(session).delete_repayment(repayment_id, loan_id=loan_id):
        raise NotFoundError(f"Repayment {repayment_id} not found on loan {loan_id}")
