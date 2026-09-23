# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column types that encrypt their value before it reaches the database.

Today one column uses this: the TOTP shared secret. A shared secret sitting in
plain text next to the password hash it is meant to back up would make the
second factor worth exactly as much as the first one to anyone holding the
SQLite file.

The key comes from a *source* rather than from settings directly. Right now the
source derives a key from ``KALETA_SECRET_KEY``; when
``docs/plans/hosted-field-encryption.md`` lands, the per-tenant key ring
replaces the source with :func:`set_key_source` and every column written by
this type moves with it — the on-disk format already carries a format byte so
the reader can tell the generations apart.

Rotating ``KALETA_SECRET_KEY`` therefore invalidates every value stored here.
For the TOTP secret that means re-enrolling, and ``kaleta --reset-password
--disable-mfa`` is the way out.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Dialect, LargeBinary
from sqlalchemy.types import TypeDecorator

from kaleta.config import settings
from kaleta.exceptions import EncryptionError

#: A callable that returns the 32-byte key every :class:`EncryptedString`
#: column encrypts under.
KeySource = Callable[[], bytes]

#: Plain UTF-8 — written only by a future ``KALETA_ENCRYPTION=off``, accepted
#: by the reader from the first day so that switching encryption on later does
#: not orphan the rows written before.
FORMAT_PLAINTEXT = 0x00
#: AES-256-GCM, 12-byte nonce, AAD = the column's name.
FORMAT_AES_GCM = 0x01

_NONCE_BYTES = 12
_KEY_BYTES = 32
_HKDF_INFO = b"kaleta-column-encryption-v1"


def _key_from_settings() -> bytes:
    """Derive the column key from ``KALETA_SECRET_KEY``.

    Read at call time, not at import time: tests and the future key ring both
    need the key to follow the setting rather than the module's birth.
    """
    return HKDF(algorithm=SHA256(), length=_KEY_BYTES, salt=None, info=_HKDF_INFO).derive(
        settings.secret_key.encode("utf-8")
    )


_key_source: KeySource = _key_from_settings


def set_key_source(source: KeySource) -> None:
    """Swap where the column key comes from (the hosted key ring, or a test)."""
    global _key_source  # noqa: PLW0603 — one process-wide key source by design
    _key_source = source


def reset_key_source() -> None:
    """Restore the ``KALETA_SECRET_KEY`` derivation."""
    set_key_source(_key_from_settings)


class EncryptedString(TypeDecorator[str]):
    """``str`` in Python, an authenticated ciphertext blob in the database."""

    impl = LargeBinary
    cache_ok = True

    def __init__(self, aad: str) -> None:
        """``aad`` is the column's fully qualified name, e.g. ``user_mfa.totp_secret``.

        It is authenticated but not encrypted, so a ciphertext copied from one
        column into another fails to decrypt instead of silently working.
        """
        super().__init__()
        # Public, plain, and a positional-or-keyword argument, all three of
        # which SQLAlchemy needs to find it: it builds a TypeDecorator's
        # static cache key from the constructor arguments it can see on the
        # instance, skipping keyword-only and underscored ones. Hidden any of
        # those ways, the `cache_ok` above would be a lie the moment a second
        # column used this type with a different AAD — two instances that
        # must not share a bind processor would look identical to the
        # statement cache.
        self.aad = aad

    @property
    def _authenticated_data(self) -> bytes:
        return self.aad.encode("utf-8")

    def process_bind_param(self, value: str | bytes | None, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            # Already a stored ciphertext. The one caller is the backup
            # restore, which carries rows out of the database and back in
            # without ever decrypting them — re-encrypting here would turn a
            # restored secret into noise that only looks fine.
            #
            # Narrow on purpose: anything that is not a ciphertext this type
            # wrote is refused rather than stored. A passthrough for arbitrary
            # bytes would make ``b"\x00" + secret`` a way to write a plaintext
            # value that the reader then happily accepts, which is the whole
            # thing this column exists to prevent. An attacker who can hand
            # this column bytes — the backup file is the way in — cannot forge
            # a ciphertext without the key, but could trivially pick a
            # plaintext, so the two are not equivalent.
            #
            # The asymmetry is deliberate and is the known cost:
            # ``process_result_value`` accepts ``FORMAT_PLAINTEXT`` so that the
            # ``KALETA_ENCRYPTION=off`` generation ADR-35 describes will not
            # orphan rows, but until something actually writes that byte there
            # is no such row to restore. When that setting lands, this writer
            # has to learn to mint ``\x00`` under it; widening the passthrough
            # now would open the hole years before the caller exists.
            # See ADR-36, "the passthrough runs one way only".
            if value[:1] != bytes([FORMAT_AES_GCM]):
                msg = "Refusing to store a value that is not an encrypted payload"
                raise EncryptionError(msg)
            return value
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = AESGCM(_key_source()).encrypt(
            nonce, value.encode("utf-8"), self._authenticated_data
        )
        return bytes([FORMAT_AES_GCM]) + nonce + ciphertext

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if not value:
            msg = "Encrypted column holds an empty value"
            raise EncryptionError(msg)
        marker, body = value[0], value[1:]
        if marker == FORMAT_PLAINTEXT:
            return body.decode("utf-8")
        if marker != FORMAT_AES_GCM:
            msg = f"Unknown encrypted column format {marker:#04x}"
            raise EncryptionError(msg)
        nonce, ciphertext = body[:_NONCE_BYTES], body[_NONCE_BYTES:]
        try:
            plain = AESGCM(_key_source()).decrypt(nonce, ciphertext, self._authenticated_data)
            return plain.decode("utf-8")
        except InvalidTag as exc:
            msg = (
                "Could not decrypt a stored secret. This happens when "
                "KALETA_SECRET_KEY changed after the value was written."
            )
            raise EncryptionError(msg) from exc
