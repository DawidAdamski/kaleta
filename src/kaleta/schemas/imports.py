# SPDX-License-Identifier: AGPL-3.0-or-later
"""Responses of ``POST /api/v1/imports`` (plan ``import-api-endpoint``)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from kaleta.models.transaction import TransactionType


class TransferWindow(BaseModel):
    """The span of the file's rows, widened by the transfer pairing window."""

    date_from: datetime.date
    date_to: datetime.date


class ImportRowPreview(BaseModel):
    """One parsed row as the import would store it."""

    row_index: int = Field(description="0-based position of the row in the file")
    date: datetime.date
    amount: Decimal
    type: TransactionType
    description: str = Field(description="The importer's final description")
    category_id: int | None
    payee_name: str | None
    duplicate: bool = Field(description="True when the import would skip it as a duplicate")


class ImportDryRunResponse(BaseModel):
    account_id: int
    profile: str
    rows: list[ImportRowPreview]
    new_payee_names: list[str] = Field(description="Payees the import would create")
    transfer_window: TransferWindow | None


class ImportSkippedRow(BaseModel):
    row_index: int
    reason: str


class ImportResponse(BaseModel):
    import_run_id: int
    account_id: int
    imported_count: int
    skipped_count: int
    skipped: list[ImportSkippedRow] = Field(
        description="Rows not imported, and why. Empty on a replay, which reports only the count."
    )
    transfer_window: TransferWindow | None
    replayed: bool = Field(
        default=False,
        description="True when this repeats an earlier request with the same Idempotency-Key",
    )
