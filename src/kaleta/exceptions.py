# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain exception hierarchy for Kaleta services."""

from __future__ import annotations


class KaletaError(Exception):
    """Base for expected domain errors surfaced to users."""

    code: str = "kaleta_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.message = message
        if code is not None:
            self.code = code
        super().__init__(message)


class NotFoundError(KaletaError):
    code = "not_found"


class ValidationError(KaletaError):
    code = "validation_error"


class ConflictError(KaletaError):
    code = "conflict"


class ImportError_(KaletaError):  # noqa: N801, N818
    """CSV / bank import parse failures (not Python's built-in ImportError)."""

    code = "import_error"


class ForecastUnavailableError(KaletaError):
    code = "forecast_unavailable"


class ExternalServiceError(KaletaError):
    """Remote dependency unreachable or returned an unusable response."""

    code = "external_service"


class UnauthorizedError(KaletaError):
    code = "unauthorized"


class MigrationError(KaletaError):
    """Schema cannot be brought to the installed alembic head safely."""

    code = "migration_error"


class SetupRequiredError(KaletaError):
    """Database has not been chosen yet — complete first-run setup in the UI."""

    code = "setup_required"


def kaleta_error_http_status(exc: KaletaError) -> int:
    """Map domain errors to HTTP status codes (shared by API handlers and event capture)."""
    if isinstance(exc, UnauthorizedError):
        return 401
    if isinstance(exc, SetupRequiredError):
        return 503
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, (ForecastUnavailableError, ExternalServiceError, MigrationError)):
        return 503
    return 500
