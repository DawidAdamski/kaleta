# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transfer pairs: suggest, accept and dismiss, as the import review does."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.exceptions import ValidationError
from kaleta.schemas.transaction import TransactionResponse
from kaleta.schemas.transfer_pair import (
    TransferPairLeg,
    TransferPairRequest,
    TransferPairResponse,
    TransferPairSuggestionResponse,
)
from kaleta.services.transaction_service import (
    DEFAULT_TRANSFER_AMOUNT_TOLERANCE,
    DEFAULT_TRANSFER_PAIRING_DAYS,
    TransactionService,
    TransferPairSuggestion,
)

#: The widest date range one suggestion request may cover.
MAX_SUGGESTION_SPAN_DAYS = 92

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"description": "A transaction does not exist"},
    409: {"description": "A leg is already linked to another row"},
    422: {"description": "The rows cannot be one transfer (currency, amount, roles)"},
}

router = APIRouter(prefix="/transfer-pairs", tags=["Transfer pairs"])


def _suggestion_response(s: TransferPairSuggestion) -> TransferPairSuggestionResponse:
    return TransferPairSuggestionResponse(
        outgoing=TransferPairLeg(
            id=s.outgoing_id,
            account_id=s.outgoing_account_id,
            date=s.outgoing_date,
            amount=s.outgoing_amount,
            description=s.outgoing_description,
        ),
        incoming=TransferPairLeg(
            id=s.incoming_id,
            account_id=s.incoming_account_id,
            date=s.incoming_date,
            amount=s.incoming_amount,
            description=s.incoming_description,
        ),
        amount=s.amount,
        currency=s.currency,
    )


@router.get(
    "/suggestions",
    response_model=list[TransferPairSuggestionResponse],
    summary="Suggest transfer pairs",
    description=(
        "Pairs of unlinked rows on two of your accounts, in the same currency, with the "
        "same amount (within `amount_tolerance`) at most `max_days_apart` days apart, one "
        "leaving and one arriving. Nothing is written. Dismissed pairs are not returned. "
        f"`date_from` and `date_to` are required and may span at most "
        f"{MAX_SUGGESTION_SPAN_DAYS} days."
    ),
)
async def suggest_transfer_pairs(
    date_from: datetime.date = Query(..., description="First day considered (inclusive)"),
    date_to: datetime.date = Query(..., description="Last day considered (inclusive)"),
    max_days_apart: int = Query(
        DEFAULT_TRANSFER_PAIRING_DAYS, ge=1, le=14, description="Most days between the legs"
    ),
    amount_tolerance: Decimal = Query(
        DEFAULT_TRANSFER_AMOUNT_TOLERANCE, ge=0, description="Largest amount difference"
    ),
    session: AsyncSession = Depends(get_session),
) -> list[TransferPairSuggestionResponse]:
    if date_to < date_from:
        raise ValidationError("date_to must not be before date_from.")
    if (date_to - date_from).days > MAX_SUGGESTION_SPAN_DAYS:
        raise ValidationError(f"The date range may span at most {MAX_SUGGESTION_SPAN_DAYS} days.")
    suggestions = await TransactionService(session).suggest_transfer_pairs(
        max_days_apart=max_days_apart,
        amount_tolerance=amount_tolerance,
        date_from=date_from,
        date_to=date_to,
    )
    return [_suggestion_response(s) for s in suggestions]


@router.post(
    "/",
    response_model=TransferPairResponse,
    summary="Pair two rows as one transfer",
    description=(
        "Turns two existing rows into the two legs of one internal transfer: both become "
        "`type=transfer`, flagged internal, without a category, linked to each other. "
        "The ids may come in either order; the rows' types say which leg is which. "
        "Two rows already linked to each other are returned unchanged, so a retry is safe.\n\n"
        "There is no unpairing yet: a wrong pair is fixed by editing both legs "
        "(`PUT /api/v1/transactions/{id}`)."
    ),
    responses=_ERRORS,
)
async def accept_transfer_pair(
    data: TransferPairRequest,
    session: AsyncSession = Depends(get_session),
) -> TransferPairResponse:
    first, second = data.transaction_ids
    outgoing, incoming = await TransactionService(session).pair_selected_as_transfer(first, second)
    return TransferPairResponse(
        outgoing=TransactionResponse.model_validate(outgoing),
        incoming=TransactionResponse.model_validate(incoming),
    )


@router.post(
    "/dismiss",
    status_code=204,
    summary="Dismiss a suggested pair",
    description=(
        "Records that the two rows are not one transfer, so they are not suggested again. "
        "The ids may come in either order. Repeating the call changes nothing."
    ),
    responses=_ERRORS,
)
async def dismiss_transfer_pair(
    data: TransferPairRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    first, second = data.transaction_ids
    await TransactionService(session).dismiss_transfer_pair(first, second)
