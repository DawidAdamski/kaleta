# SPDX-License-Identifier: AGPL-3.0-or-later
"""The column type that keeps secrets out of the database file."""

from __future__ import annotations

import pytest
from sqlalchemy import Dialect

from kaleta.db import types as types_mod
from kaleta.db.types import FORMAT_AES_GCM, FORMAT_PLAINTEXT, EncryptedString
from kaleta.exceptions import EncryptionError

DIALECT: Dialect = None  # type: ignore[assignment]  # the type never looks at it


@pytest.fixture
def column() -> EncryptedString:
    return EncryptedString(aad="user_mfa.totp_secret")


@pytest.fixture(autouse=True)
def fixed_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(types_mod, "_key_source", lambda: b"k" * 32)


class TestRoundTrip:
    def test_a_value_survives_the_journey(self, column: EncryptedString) -> None:
        stored = column.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        assert column.process_result_value(stored, DIALECT) == "JBSWY3DPEHPK3PXP"

    def test_none_stays_none(self, column: EncryptedString) -> None:
        assert column.process_bind_param(None, DIALECT) is None
        assert column.process_result_value(None, DIALECT) is None

    def test_the_ciphertext_does_not_contain_the_value(self, column: EncryptedString) -> None:
        stored = column.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        assert b"JBSWY3DPEHPK3PXP" not in stored
        assert stored[0] == FORMAT_AES_GCM

    def test_the_same_value_encrypts_differently_every_time(self, column: EncryptedString) -> None:
        """A fresh nonce per write; two identical secrets must not look alike."""
        first = column.process_bind_param("same", DIALECT)
        second = column.process_bind_param("same", DIALECT)
        assert first != second


class TestTampering:
    def test_a_flipped_byte_is_refused(self, column: EncryptedString) -> None:
        stored = column.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        broken = bytearray(stored)
        broken[-1] ^= 0x01
        with pytest.raises(EncryptionError):
            column.process_result_value(bytes(broken), DIALECT)

    def test_a_ciphertext_from_another_column_is_refused(self) -> None:
        """The column name is authenticated, so blobs cannot be swapped around."""
        source = EncryptedString(aad="user_mfa.totp_secret")
        other = EncryptedString(aad="somewhere.else")
        stored = source.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        with pytest.raises(EncryptionError):
            other.process_result_value(stored, DIALECT)

    def test_a_changed_key_is_refused_with_an_explanation(
        self, column: EncryptedString, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stored = column.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        monkeypatch.setattr(types_mod, "_key_source", lambda: b"j" * 32)
        with pytest.raises(EncryptionError, match="KALETA_SECRET_KEY"):
            column.process_result_value(stored, DIALECT)

    def test_an_unknown_format_byte_is_refused(self, column: EncryptedString) -> None:
        with pytest.raises(EncryptionError, match="format"):
            column.process_result_value(b"\x7f" + b"whatever", DIALECT)

    def test_an_empty_blob_is_refused(self, column: EncryptedString) -> None:
        with pytest.raises(EncryptionError):
            column.process_result_value(b"", DIALECT)


class TestPlaintextGeneration:
    def test_a_plaintext_row_is_still_readable(self, column: EncryptedString) -> None:
        """Rows written before encryption is switched on must not be orphaned."""
        legacy = bytes([FORMAT_PLAINTEXT]) + b"JBSWY3DPEHPK3PXP"
        assert column.process_result_value(legacy, DIALECT) == "JBSWY3DPEHPK3PXP"


class TestKeySource:
    def test_the_key_follows_the_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        types_mod.reset_key_source()
        monkeypatch.setattr(types_mod.settings, "secret_key", "first-secret-value")
        first = types_mod._key_source()
        monkeypatch.setattr(types_mod.settings, "secret_key", "second-secret-value")
        second = types_mod._key_source()
        assert first != second
        assert len(first) == 32

    def test_the_source_can_be_swapped_and_restored(self) -> None:
        types_mod.set_key_source(lambda: b"z" * 32)
        assert types_mod._key_source() == b"z" * 32
        types_mod.reset_key_source()
        assert types_mod._key_source() != b"z" * 32


class TestAlreadyEncryptedPassthrough:
    def test_a_stored_blob_is_not_encrypted_again(self, column: EncryptedString) -> None:
        """The backup restore carries rows back in without ever decrypting them."""
        stored = column.process_bind_param("JBSWY3DPEHPK3PXP", DIALECT)
        assert stored is not None
        assert column.process_bind_param(stored, DIALECT) == stored
        assert column.process_result_value(stored, DIALECT) == "JBSWY3DPEHPK3PXP"
