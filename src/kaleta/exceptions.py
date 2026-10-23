# SPDX-License-Identifier: AGPL-3.0-or-later
"""Domain exception hierarchy for Kaleta services."""

from __future__ import annotations


class KaletaError(Exception):
    """Base for expected domain errors surfaced to users.

    ``message`` is the English fallback: it is what logs, ``event_capture``
    and the REST API read, and what a toast shows when no translation key is
    given. ``message_key`` plus ``params`` let a raise site localize its
    *toast* without disturbing any of that — the view resolves
    ``t(message_key, **params)`` when a key is present, and falls back to
    ``message`` otherwise (see ``views.error_handling._notify_with_event``).
    Localization is opt-in per raise site, so un-migrated raises are
    unaffected.
    """

    code: str = "kaleta_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        message_key: str | None = None,
        params: dict[str, object] | None = None,
    ) -> None:
        self.message = message
        self.message_key = message_key
        self.params = params
        if code is not None:
            self.code = code
        super().__init__(message)


class NotFoundError(KaletaError):
    code = "not_found"


class ValidationError(KaletaError):
    code = "validation_error"


class ConflictError(KaletaError):
    code = "conflict"


class StaleWriteError(ConflictError):
    """The row changed since the editor loaded it (``hosted-household-sharing`` §4).

    ``changed_by`` names the member behind the newer change when one is
    recorded, so the page can say whose change would be overwritten.
    """

    code = "stale_write"

    def __init__(
        self,
        message: str,
        *,
        changed_by: str | None = None,
        message_key: str | None = None,
        params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, message_key=message_key, params=params)
        self.changed_by = changed_by


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


class EmailNotVerifiedError(UnauthorizedError):
    """The password was right, but the e-mail address has not been confirmed yet."""

    code = "email_not_verified"


class EncryptionError(KaletaError):
    """A value stored under column encryption could not be read or written."""

    code = "encryption_error"


class TenantLockedError(KaletaError):
    """The account's data key is not unlocked in this session (or for this token).

    Encrypted columns can be neither read nor written until the member gives
    their data passphrase on ``/unlock``. A bearer token cannot unlock; it
    rides on an unlock its member made in a browser session.
    """

    code = "tenant_locked"


class MigrationError(KaletaError):
    """Schema cannot be brought to the installed alembic head safely."""

    code = "migration_error"


def kaleta_error_http_status(exc: KaletaError) -> int:
    """Map domain errors to HTTP status codes (shared by API handlers and event capture)."""
    if isinstance(exc, UnauthorizedError):
        return 401
    if isinstance(exc, TenantLockedError):
        return 423
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, ConflictError):
        return 409
    if isinstance(exc, (ForecastUnavailableError, ExternalServiceError, MigrationError)):
        return 503
    return 500
