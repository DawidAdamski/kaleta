"""Map domain exceptions to NiceGUI user feedback."""

from __future__ import annotations

from nicegui import ui

from kaleta.exceptions import KaletaError


def notify_kaleta_error(exc: KaletaError) -> None:
    """Show a negative toast for a handled domain error."""
    ui.notify(exc.message, type="negative")


def handle_kaleta_error(exc: Exception) -> bool:
    """Return True when *exc* is a :class:`KaletaError` and was shown to the user."""
    if isinstance(exc, KaletaError):
        notify_kaleta_error(exc)
        return True
    return False
