# SPDX-License-Identifier: AGPL-3.0-or-later
"""``POST /api/v1/imports`` — import one bank statement through the pipeline.

The body is the raw file, never multipart: FastAPI parses form data before the
router's auth dependency runs, and Starlette spools large parts to disk. Here
the route reads nothing until ``require_api_auth`` has passed, refuses an
oversized ``Content-Length`` up front, and counts bytes as it streams so a lying
or absent header cannot get past ``settings.max_upload_bytes`` either. The body
stays in memory only.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.api.deps import get_session
from kaleta.config import settings
from kaleta.exceptions import PayloadTooLargeError, ValidationError
from kaleta.schemas.imports import (
    ImportDryRunResponse,
    ImportResponse,
    ImportRowPreview,
    ImportSkippedRow,
    TransferWindow,
)
from kaleta.services.import_pipeline import (
    ImportOptions,
    ImportPipeline,
    upload_exceeds_limit,
)

router = APIRouter(prefix="/imports", tags=["Imports"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not authenticated"},
    409: {"description": "Ambiguous account number, or the same file already imported"},
    413: {"description": "Body over the byte cap, or more rows than the row cap"},
    422: {"description": "Not ready: no account, no categories, currency mismatch, unmapped CSV"},
    423: {"description": "The token owner's data is locked"},
}


def _window(window: tuple[datetime.date, datetime.date] | None) -> TransferWindow | None:
    return None if window is None else TransferWindow(date_from=window[0], date_to=window[1])


async def _read_body(request: Request) -> bytes:
    """The request body, refused with 413 as soon as it passes the byte cap."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            size = int(declared)
        except ValueError:
            raise ValidationError("Content-Length is not a number.") from None
        if upload_exceeds_limit(size):
            raise PayloadTooLargeError(
                f"The file is larger than the {settings.max_upload_bytes}-byte upload limit."
            )
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if upload_exceeds_limit(total):
            raise PayloadTooLargeError(
                f"The file is larger than the {settings.max_upload_bytes}-byte upload limit."
            )
        chunks.append(chunk)
    body = b"".join(chunks)
    if not body:
        raise ValidationError("The request body is empty: send the statement file as the body.")
    return body


@router.post(
    "/",
    response_model=ImportResponse | ImportDryRunResponse,
    status_code=201,
    summary="Import a bank statement",
    description=(
        "Imports one bank statement the way the import page does: the bank profile is "
        "detected, the account is resolved (`account_id`, else a saved filename rule, else "
        "the mBank statement's account number), descriptions take the importer's format, "
        "own-account transfers are detected, duplicates are skipped and categorisation "
        "rules are applied. Everything is written in one transaction, with an import run "
        "that shows in *Account coverage and recent imports*.\n\n"
        "Send the file itself as the body (`Content-Type: text/csv` or "
        "`application/octet-stream`), not multipart. Bodies over `KALETA_MAX_UPLOAD_BYTES` "
        "and files with more rows than `KALETA_API_IMPORT_MAX_ROWS` get `413`.\n\n"
        "- `dry_run=true` returns the rows as they would be stored and writes nothing (`200`).\n"
        "- An `Idempotency-Key` header makes a repeat return the first result (`200`, "
        "`replayed: true`) without importing again.\n"
        "- The same file again for the same account is refused with `409` naming the earlier "
        "import run, unless `allow_reimport=true`.\n"
        "- A generic CSV needs a column mapping saved for its filename on the import page; "
        "without one the `422` lists the headers found.\n\n"
        "With encryption enabled, a bearer token imports only while its owner has an unlocked "
        "browser session; otherwise `423`."
    ),
    responses=_ERRORS,
)
async def create_import(
    request: Request,
    response: Response,
    filename: str = Query(
        ..., min_length=1, max_length=255, description="Used for rules and the import run"
    ),
    account_id: int | None = Query(None, description="Target account; resolved when omitted"),
    default_expense_category_id: int = Query(...),
    default_income_category_id: int = Query(...),
    skip_duplicates: bool = Query(True),
    dry_run: bool = Query(False),
    allow_reimport: bool = Query(False, description="Import a file already imported here"),
    idempotency_key: str | None = Header(
        None, alias="Idempotency-Key", min_length=1, max_length=200
    ),
    session: AsyncSession = Depends(get_session),
) -> ImportResponse | ImportDryRunResponse:
    raw = await _read_body(request)
    options = ImportOptions(
        filename=filename,
        account_id=account_id,
        expense_category_id=default_expense_category_id,
        income_category_id=default_income_category_id,
        skip_duplicates=skip_duplicates,
    )
    pipeline = ImportPipeline(session)
    if dry_run:
        plan = await pipeline.preview_upload(raw, options)
        response.status_code = 200
        return ImportDryRunResponse(
            account_id=plan.account_id,
            profile=plan.profile,
            rows=[
                ImportRowPreview(
                    row_index=r.row_index,
                    date=r.date,
                    amount=r.amount,
                    type=r.type,
                    description=r.description,
                    category_id=r.category_id,
                    payee_name=r.payee_name,
                    duplicate=r.duplicate,
                )
                for r in await pipeline.preview_rows(plan)
            ],
            new_payee_names=plan.new_payee_names,
            transfer_window=_window(plan.transfer_window),
        )
    outcome = await pipeline.import_upload(
        raw, options, idempotency_key=idempotency_key, allow_reimport=allow_reimport
    )
    if outcome.replayed:
        response.status_code = 200
    return ImportResponse(
        import_run_id=outcome.import_run_id,
        account_id=outcome.account_id,
        imported_count=outcome.imported_count,
        skipped_count=outcome.skipped_count,
        skipped=[ImportSkippedRow(row_index=s.row_index, reason=s.reason) for s in outcome.skipped],
        transfer_window=_window(outcome.transfer_window),
        replayed=outcome.replayed,
    )
