# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared API error envelope and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kaleta.exceptions import (
    KaletaError,
    kaleta_error_http_status,
)

log = logging.getLogger(__name__)


def error_envelope(*, code: str, message: str, event_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if event_id:
        body["event_id"] = event_id
    return {"error": body}


def _code_from_http_status(status: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        503: "service_unavailable",
    }.get(status, "error")


def _message_from_http_detail(detail: Any) -> tuple[str, str]:
    if isinstance(detail, dict):
        code = str(detail.get("code") or detail.get("error") or "error")
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        return code, message
    if isinstance(detail, list):
        return "validation_error", "Request validation failed"
    return "error", str(detail)


def _status_for(exc: KaletaError) -> int:
    return kaleta_error_http_status(exc)


async def kaleta_error_handler(request: Request, exc: KaletaError) -> JSONResponse:
    status = _status_for(exc)
    event_id: str | None = None
    if status >= 500:
        log.exception("Unhandled domain error: %s", exc.message)
        from kaleta.services.event_capture import capture_exception_async

        event_id = await capture_exception_async(
            exc,
            route=str(request.url.path),
            request_id=request.headers.get("x-request-id"),
        )
    return JSONResponse(
        status_code=status,
        content=error_envelope(code=exc.code, message=exc.message, event_id=event_id),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception on %s", request.url.path)
    from kaleta.services.event_capture import capture_exception_async

    event_id = await capture_exception_async(
        exc,
        route=str(request.url.path),
        request_id=request.headers.get("x-request-id"),
    )
    return JSONResponse(
        status_code=500,
        content=error_envelope(
            code="internal_error",
            message="An unexpected error occurred.",
            event_id=event_id,
        ),
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    code, message = _message_from_http_detail(exc.detail)
    if exc.status_code == 401 and code == "error":
        code = "unauthorized"
    if code == "error" and exc.status_code in (400, 404, 409, 422, 503):
        code = _code_from_http_status(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_envelope(code=code, message=message),
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    return JSONResponse(
        status_code=422,
        content=error_envelope(
            code="validation_error",
            message=errors[0]["msg"] if errors else "Request validation failed",
        ),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install Kaleta error handlers on a FastAPI (or NiceGUI) app."""
    app.add_exception_handler(KaletaError, kaleta_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
