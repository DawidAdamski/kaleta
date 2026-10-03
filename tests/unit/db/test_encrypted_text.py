# SPDX-License-Identifier: AGPL-3.0-or-later
"""``EncryptedText`` and blind indexes, on a real table.

Covers: KAL-ENC-001, KAL-ENC-007
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, select
from sqlalchemy.exc import StatementError

from kaleta.config import settings
from kaleta.crypto import DataKey, generate_dek
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.db.types import (
    TEXT_FORMAT_AES_GCM,
    TEXT_FORMAT_PLAIN,
    EncryptedText,
    blind_index,
    blind_index_digits,
    exact_index,
    install_data_key_resolver,
    normalise_for_index,
    use_data_key,
)
from kaleta.exceptions import EncryptionError, TenantLockedError

metadata = MetaData()
notes = Table(
    "notes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("body", EncryptedText(aad="notes.body")),
    Column("other", EncryptedText(aad="notes.other")),
    Column("audit", EncryptedText(aad="notes.audit", plaintext_while_locked=True)),
    Column("body_bidx", String(64)),
)


@pytest.fixture
def engine() -> Iterator[object]:
    eng = create_engine("sqlite://")
    metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def encrypted(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Encryption on and *locked*: no key until a test supplies one.

    Removes the suite-wide test keyring the autouse fixture installs when the
    suite runs with ``KALETA_ENCRYPTION=passphrase``.
    """
    monkeypatch.setattr(settings, "encryption", "passphrase")
    install_data_key_resolver(None)
    yield


@pytest.fixture
def plain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "encryption", "off")


def _raw(engine, column: str = "body") -> bytes:  # type: ignore[no-untyped-def]
    with engine.connect() as conn:
        return conn.exec_driver_sql(f"SELECT {column} FROM notes").scalar_one()


def _write(engine, **values: object) -> None:  # type: ignore[no-untyped-def]
    with engine.begin() as conn:
        conn.execute(insert(notes).values(**values))


def _read(engine, column: str = "body") -> str | None:  # type: ignore[no-untyped-def]
    with engine.connect() as conn:
        return conn.execute(select(notes.c[column])).scalar_one()


def test_with_encryption_on_the_stored_bytes_hide_the_text(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    key = DataKey(generate_dek(), version=3)
    with use_data_key(key):
        _write(engine, body="Biedronka, Kraków")
        assert _read(engine) == "Biedronka, Kraków"

    raw = _raw(engine)
    assert raw[0] == TEXT_FORMAT_AES_GCM
    assert raw[1] == 3  # the key version travels in the header
    assert b"Biedronka" not in raw
    assert "Kraków".encode() not in raw


def test_plaintext_rows_and_ciphertext_rows_both_read(engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "encryption", "off")
    _write(engine, body="written before encryption was on")
    assert _raw(engine)[0] == TEXT_FORMAT_PLAIN

    monkeypatch.setattr(settings, "encryption", "passphrase")
    key = DataKey(generate_dek())
    with use_data_key(key):
        _write(engine, body="written after")
        with engine.connect() as conn:
            rows = conn.execute(select(notes.c.body).order_by(notes.c.id)).scalars().all()
    assert rows == ["written before encryption was on", "written after"]


def test_a_ciphertext_copied_to_another_column_does_not_decrypt(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    key = DataKey(generate_dek())
    with use_data_key(key):
        _write(engine, body="secret")
    stolen = _raw(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("UPDATE notes SET other = ?", (stolen,))

    with use_data_key(key), pytest.raises(EncryptionError):
        _read(engine, "other")


def test_another_accounts_key_reads_nothing(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    with use_data_key(DataKey(generate_dek())):
        _write(engine, body="mine")

    with use_data_key(DataKey(generate_dek())), pytest.raises(EncryptionError):
        _read(engine)


def test_a_locked_session_can_neither_read_nor_write(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    with use_data_key(DataKey(generate_dek())):
        _write(engine, body="mine")

    with pytest.raises(TenantLockedError):
        _read(engine)
    # A bind-time error reaches the caller wrapped by SQLAlchemy; the domain
    # error is its cause (the API error handler unwraps it to a 423).
    with pytest.raises(StatementError) as wrapped:
        _write(engine, body="more")
    assert isinstance(wrapped.value.orig, TenantLockedError)


def test_only_the_audit_column_may_write_plaintext_while_locked(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    _write(engine, audit='{"event": "login"}')

    assert _raw(engine, "audit")[0] == TEXT_FORMAT_PLAIN
    assert _read(engine, "audit") == '{"event": "login"}'


def test_a_key_version_mismatch_is_reported(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    dek = generate_dek()
    with use_data_key(DataKey(dek, version=1)):
        _write(engine, body="v1")

    with use_data_key(DataKey(dek, version=2)), pytest.raises(EncryptionError, match="version"):
        _read(engine)


def test_the_tenant_context_and_the_single_resolver_supply_the_key(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    key = DataKey(generate_dek())
    with use_tenant(TenantContext(tenant_id=1, schema="t_0123456789ab", key_ring=key)):
        _write(engine, body="hosted")
    install_data_key_resolver(lambda: key)
    try:
        assert _read(engine) == "hosted"
    finally:
        install_data_key_resolver(None)


def test_a_plaintext_blob_is_not_smuggled_into_an_encrypted_account(engine, encrypted) -> None:  # type: ignore[no-untyped-def]
    with use_data_key(DataKey(generate_dek())), pytest.raises(StatementError) as wrapped:
        _write(engine, body=b"\x00plaintext")
    assert isinstance(wrapped.value.orig, EncryptionError)


def test_with_encryption_off_text_is_stored_under_the_plain_format(engine, plain) -> None:  # type: ignore[no-untyped-def]
    _write(engine, body="zakupy")

    assert _raw(engine) == b"\x00zakupy"
    assert _read(engine) == "zakupy"


def test_blind_index_normalisation() -> None:
    assert normalise_for_index("  Ｂｉｅｄｒｏｎｋａ \t  Sp.  z o.o. ") == "biedronka sp. z o.o."
    assert normalise_for_index("STRASSE") == normalise_for_index("straße")


def test_blind_index_equal_after_normalising_and_keyed_by_the_data_key(encrypted) -> None:  # type: ignore[no-untyped-def]
    key_a, key_b = DataKey(generate_dek()), DataKey(generate_dek())
    with use_data_key(key_a):
        a1, a2 = blind_index("Biedronka"), blind_index("  biedronka ")
        digits = blind_index_digits("PL 61 1090 1014 0000 0712 1981 2874")
        suffix = blind_index_digits("61109010140000071219812874", last=8)
        tail = blind_index_digits("19812874")
    with use_data_key(key_b):
        b1 = blind_index("Biedronka")

    assert a1 == a2
    assert a1 is not None and len(a1) == 64
    assert a1 != b1  # another account's index says nothing about this one's
    with use_data_key(key_a):
        assert digits == blind_index_digits("61109010140000071219812874")
    assert suffix == tail
    assert blind_index(None) is None
    assert blind_index_digits("no digits here") is None


def test_blind_index_needs_the_key_when_encryption_is_on(encrypted) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TenantLockedError):
        blind_index("anything")


def test_blind_index_works_without_a_key_when_encryption_is_off(plain) -> None:  # type: ignore[no-untyped-def]
    assert blind_index("Food") == blind_index("food")


def test_exact_index_tells_case_apart(plain) -> None:  # type: ignore[no-untyped-def]
    # The name_bidx columns keep the exact uniqueness the plain names had.
    assert exact_index("Lidl") == exact_index("Lidl")
    assert exact_index("Lidl") != exact_index("LIDL")
    assert exact_index("Lidl") != blind_index("Lidl")
    assert exact_index(None) is None


def test_exact_index_depends_on_the_data_key(encrypted) -> None:  # type: ignore[no-untyped-def]
    with use_data_key(DataKey(generate_dek())):
        first = exact_index("Lidl")
    with use_data_key(DataKey(generate_dek())):
        second = exact_index("Lidl")
    assert first != second
    with pytest.raises(TenantLockedError):
        exact_index("Lidl")
