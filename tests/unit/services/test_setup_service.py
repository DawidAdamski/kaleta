# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ``setup_service`` URL helpers."""

from __future__ import annotations

from kaleta.services.setup_service import _sync_url


class TestSyncUrl:
    """``_sync_url`` rebuilds the sync (psycopg2) URL structurally.

    The driver is swapped with ``URL.set`` rather than a whole-string replace,
    and asyncpg's ``ssl=`` TLS argument is translated to psycopg2's ``sslmode=``.
    """

    def test_password_containing_async_driver_token_survives(self) -> None:
        """A password with the ``+asyncpg`` substring is not corrupted."""
        assert (
            _sync_url("postgresql+asyncpg://user:s3cret+asyncpg@host:5432/db")
            == "postgresql+psycopg2://user:s3cret+asyncpg@host:5432/db"
        )

    def test_driver_switched_to_sync(self) -> None:
        """The async driver becomes the explicit psycopg2 sync driver."""
        assert (
            _sync_url("postgresql+asyncpg://user:pass@host:5432/db")
            == "postgresql+psycopg2://user:pass@host:5432/db"
        )

    def test_bare_postgresql_pinned_to_psycopg2(self) -> None:
        """A driverless ``postgresql://`` URL is pinned to psycopg2."""
        assert (
            _sync_url("postgresql://user:pass@host:5432/db")
            == "postgresql+psycopg2://user:pass@host:5432/db"
        )

    def test_ssl_require_becomes_sslmode_require(self) -> None:
        """asyncpg ``ssl=require`` is translated to psycopg2 ``sslmode=require``."""
        assert (
            _sync_url("postgresql+asyncpg://user:pass@host:5432/db?ssl=require")
            == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
        )

    def test_ssl_boolean_true_maps_to_require(self) -> None:
        """asyncpg accepts booleans: ``ssl=true`` means require TLS."""
        assert (
            _sync_url("postgresql+asyncpg://user:pass@host:5432/db?ssl=true")
            == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=require"
        )

    def test_ssl_boolean_false_maps_to_disable(self) -> None:
        """asyncpg ``ssl=false`` means no TLS, i.e. ``sslmode=disable``."""
        assert (
            _sync_url("postgresql+asyncpg://user:pass@host:5432/db?ssl=false")
            == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=disable"
        )

    def test_unknown_ssl_value_passes_through(self) -> None:
        """An unrecognised TLS value is passed through unchanged, not guessed."""
        assert (
            _sync_url("postgresql+asyncpg://user:pass@host:5432/db?ssl=verify-full")
            == "postgresql+psycopg2://user:pass@host:5432/db?sslmode=verify-full"
        )

    def test_no_ssl_arg_stays_ssl_free(self) -> None:
        """A URL without a TLS argument gains no ``sslmode``."""
        result = _sync_url("postgresql+asyncpg://user:pass@host:5432/db")
        assert "sslmode" not in result
        assert "ssl" not in result

    def test_non_postgresql_url_returned_unchanged(self) -> None:
        """Non-postgresql URLs are left exactly as given."""
        assert _sync_url("sqlite:///tmp/x.db") == "sqlite:///tmp/x.db"
