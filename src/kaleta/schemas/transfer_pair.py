# SPDX-License-Identifier: AGPL-3.0-or-later
"""Request and response bodies of ``/api/v1/transfer-pairs``."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from kaleta.schemas.transaction import TransactionResponse


class TransferPairLeg(BaseModel):
    """One side of a suggested transfer, as much as a client needs to decide."""

    id: int
    account_id: int
    date: datetime.date
    amount: Decimal
    description: str


class TransferPairSuggestionResponse(BaseModel):
    """Two unlinked rows that look like one transfer between own accounts."""

    outgoing: TransferPairLeg
    incoming: TransferPairLeg
    amount: Decimal
    currency: str


class TransferPairRequest(BaseModel):
    """The two rows of a pair, in either order: their types say which leg is which."""

    transaction_ids: list[int] = Field(min_length=2, max_length=2)


class TransferPairResponse(BaseModel):
    """Both legs of a transfer after it was paired."""

    outgoing: TransactionResponse
    incoming: TransactionResponse
