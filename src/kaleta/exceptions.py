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


class UnauthorizedError(KaletaError):
    code = "unauthorized"
