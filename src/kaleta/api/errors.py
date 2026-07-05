"""Shared API error envelope and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kaleta.exceptions import (
    ConflictError,
    ForecastUnavailableError,
    KaletaError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)

log = logging.getLogger(__name__)

_STATUS_BY_TYPE: dict[type[KaletaError], int] = {
    UnauthorizedError: 401,
}


def error_envelope(*, code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _status_for(exc: KaletaError) -> int:
    for cls, status in _STATUS_BY_TYPE.items():
        if isinstance(exc, cls):
            return status

    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, ForecastUnavailableError):
        return 503
    return 500


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


async def kaleta_error_handler(_request: Request, exc: KaletaError) -> JSONResponse:
    status = _status_for(exc)
    if status >= 500:
        log.exception("Unhandled domain error: %s", exc.message)
    return JSONResponse(
        status_code=status,
        content=error_envelope(code=exc.code, message=exc.message),
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
