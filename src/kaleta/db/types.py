# SPDX-License-Identifier: AGPL-3.0-or-later
"""Column types that encrypt their value before it reaches the database.

Today one column uses this: the TOTP shared secret. A shared secret sitting in
plain text next to the password hash it is meant to back up would make the
second factor worth exactly as much as the first one to anyone holding a
copy of the database.

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

import hashlib
import hmac
import json
import os
import re
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import Dialect, LargeBinary
from sqlalchemy.types import TypeDecorator

from kaleta.config import settings
from kaleta.crypto import DataKey
from kaleta.db.tenant_context import current_tenant
from kaleta.exceptions import EncryptionError, TenantLockedError

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
    global _key_source  # one process-wide key source by design
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


# ── Field-level encryption under the account's data key ──────────────────────
#
# ``EncryptedString`` above protects one *server* secret (the TOTP seed) under
# a key derived from ``KALETA_SECRET_KEY``. ``EncryptedText`` below protects
# the *user's* text under the data key only an unlocked session holds
# (``hosted-field-encryption``): the operator, holding ``KALETA_SECRET_KEY``
# and the database, still cannot read it.

#: Plain UTF-8: ``KALETA_ENCRYPTION=off``, and rows written before it was on.
TEXT_FORMAT_PLAIN = 0x00
#: AES-256-GCM under the data key: ``\x01``, one key-version byte, a 12-byte
#: nonce, then ciphertext and tag. AAD = ``table.column``.
TEXT_FORMAT_AES_GCM = 0x01

DataKeyResolver = Callable[[], DataKey | None]

_explicit_key: ContextVar[DataKey | None] = ContextVar("kaleta_data_key", default=None)
_key_resolver: DataKeyResolver | None = None


def install_data_key_resolver(resolver: DataKeyResolver | None) -> None:
    """Where code with no family context finds the unlocked data key.

    A family's sessions carry it on ``TenantContext.key_ring``, which wins
    whenever a context is set; this answers only outside one.
    """
    global _key_resolver  # one process-wide resolver by design, like the tenant one
    _key_resolver = resolver


@contextmanager
def use_data_key(key: DataKey | None) -> Iterator[None]:
    """Encrypt and decrypt under ``key`` for the duration of the block (scripts, tests)."""
    token = _explicit_key.set(key)
    try:
        yield
    finally:
        _explicit_key.reset(token)


def set_data_key(key: DataKey | None) -> None:
    """Bind ``key`` to the current context until it ends — the API dependency's form.

    ``use_data_key`` for code that has no ``with`` around the work it guards:
    a FastAPI dependency runs in the request's context, so what it sets here is
    what the route's services see, the way ``set_tenant`` works.
    """
    _explicit_key.set(key)


def current_data_key() -> DataKey | None:
    """The data key for this request, task or block — ``None`` when locked."""
    explicit = _explicit_key.get()
    if explicit is not None:
        return explicit
    ctx = current_tenant()
    if ctx is not None:
        return ctx.key_ring
    if _key_resolver is not None:
        return _key_resolver()
    return None


def _locked() -> TenantLockedError:
    return TenantLockedError("Unlock your data with your passphrase first.")


def _require_key() -> DataKey:
    key = current_data_key()
    if key is None:
        raise _locked()
    return key


class EncryptedText(TypeDecorator[str]):
    """``str`` in Python; ciphertext (or format-``\\x00`` plaintext) in the database.

    Nothing but ``IS NULL`` may be asked of such a column in SQL: equality on
    ciphertext never matches (every write has a fresh nonce), and ordering or
    ``LIKE`` on bytes is meaningless. Equality goes through a ``*_bidx``
    column (:func:`blind_index`); search and sort happen in Python.
    """

    impl = LargeBinary
    cache_ok = True

    def __init__(self, aad: str, plaintext_while_locked: bool = False) -> None:
        """``aad`` is ``table.column``; it binds a ciphertext to the column it was written to.

        ``plaintext_while_locked`` is for ``audit_log`` alone: authentication
        events are written before the account is unlocked (a sign-in, a
        second-factor check) and carry nothing the operator does not already
        hold — an e-mail address and an event name — so they are stored under
        the plaintext format byte rather than refused. Everything written
        after the unlock is encrypted like any other column.
        """
        super().__init__()
        # Public and positional-or-keyword for SQLAlchemy's cache key, exactly
        # as ``EncryptedString.aad`` (see there).
        self.aad = aad
        self.plaintext_while_locked = plaintext_while_locked

    def process_bind_param(self, value: str | bytes | None, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            # A stored value carried through untouched (backup restore). Only
            # a ciphertext passes while encryption is on: a plaintext blob
            # handed in would otherwise land unencrypted in an encrypted
            # account. With encryption off either format is accepted, so a
            # database can be restored from before it was switched off.
            allowed = {TEXT_FORMAT_AES_GCM}
            if not settings.encryption_enabled:
                allowed.add(TEXT_FORMAT_PLAIN)
            if not value or value[0] not in allowed:
                msg = "Refusing to store a value that is not an encrypted payload"
                raise EncryptionError(msg)
            return value
        plain = value.encode("utf-8")
        if not settings.encryption_enabled:
            return bytes([TEXT_FORMAT_PLAIN]) + plain
        key = current_data_key()
        if key is None:
            if self.plaintext_while_locked:
                return bytes([TEXT_FORMAT_PLAIN]) + plain
            raise _locked()
        nonce = os.urandom(_NONCE_BYTES)
        sealed = _aead(key.dek).encrypt(nonce, plain, self.aad.encode("utf-8"))
        return bytes([TEXT_FORMAT_AES_GCM, key.version]) + nonce + sealed

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        value = bytes(value)
        if not value:
            msg = "Encrypted column holds an empty value"
            raise EncryptionError(msg)
        marker = value[0]
        if marker == TEXT_FORMAT_PLAIN:
            return value[1:].decode("utf-8")
        if marker != TEXT_FORMAT_AES_GCM:
            msg = f"Unknown encrypted column format {marker:#04x}"
            raise EncryptionError(msg)
        key = _require_key()
        version = value[1]
        if version != key.version:
            msg = (
                f"This value was written under key version {version}; "
                f"the unlocked key is version {key.version}."
            )
            raise EncryptionError(msg)
        nonce, body = value[2 : 2 + _NONCE_BYTES], value[2 + _NONCE_BYTES :]
        try:
            return _aead(key.dek).decrypt(nonce, body, self.aad.encode("utf-8")).decode("utf-8")
        except InvalidTag as exc:
            msg = f"Could not decrypt {self.aad}: wrong key, or the value was moved or damaged."
            raise EncryptionError(msg) from exc


@lru_cache(maxsize=8)
def _aead(dek: bytes) -> AESGCM:
    """One AES-GCM context per key: the key schedule is the expensive part of a small value."""
    return AESGCM(dek)


# ── Blind indexes ─────────────────────────────────────────────────────────────

#: The index key while encryption is off. Public on purpose — there is nothing
#: to hide in a database that stores the plaintext next to it — and present so
#: equality and uniqueness go through the same ``*_bidx`` column in both modes:
#: an ``EncryptedText`` column is bytes either way, so SQL ``lower()`` and
#: collations no longer apply to it.
_PLAIN_INDEX_KEY = HKDF(
    algorithm=SHA256(), length=_KEY_BYTES, salt=None, info=b"kaleta-blind-index-plaintext"
).derive(b"\x00" * _KEY_BYTES)

_WHITESPACE = re.compile(r"\s+")


def normalise_for_index(value: str) -> str:
    """NFKC, case-folded, whitespace collapsed and trimmed."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def digits_only(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKC", value) if ch.isascii() and ch.isdigit()
    )


def _index_key() -> bytes:
    if not settings.encryption_enabled:
        return _PLAIN_INDEX_KEY
    return _require_key().index_key


def _hmac(normalised: str) -> str:
    return hmac.new(_index_key(), normalised.encode("utf-8"), hashlib.sha256).hexdigest()


def blind_index(value: str | None) -> str | None:
    """Hex HMAC-SHA256 of the normalised value — equality without the plaintext."""
    if value is None:
        return None
    return _hmac(normalise_for_index(value))


def exact_index(value: str | None) -> str | None:
    """Hex HMAC-SHA256 of the value exactly as written — the ``name_bidx`` columns.

    Not normalised, unlike ``blind_index``: those columns carry the unique
    constraints and lookups the plain ``name`` columns had, and those compared
    exactly. A normalised one would make "LIDL" and "Lidl" collide — the very
    pairs the dedupe screens exist to find — and would make the migration fail
    on a database that holds them. The ``=`` keeps it apart from both other
    index kinds under the same key.
    """
    if value is None:
        return None
    return _hmac("=" + value)


def blind_index_digits(value: str | None, *, last: int | None = None) -> str | None:
    """The index of a number's digits (all, or the ``last`` few); ``None`` when it has none."""
    if value is None:
        return None
    digits = digits_only(value)
    if last is not None:
        digits = digits[-last:]
    if not digits:
        return None
    return _hmac("#" + digits)


#: ADR-20 matches a counterparty account by its last eight digits.
ACCOUNT_SUFFIX_DIGITS = 8


def account_suffix_index(value: str | None) -> str | None:
    """The blind index of an account number's last ``ACCOUNT_SUFFIX_DIGITS`` digits."""
    return blind_index_digits(value, last=ACCOUNT_SUFFIX_DIGITS)


class EncryptedJSON(TypeDecorator[Any]):
    """A JSON document stored as ``EncryptedText`` — for snapshots that carry user text."""

    impl = LargeBinary
    cache_ok = True

    def __init__(self, aad: str) -> None:
        super().__init__()
        self.aad = aad
        self._text = EncryptedText(aad)

    def process_bind_param(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return self._text.process_bind_param(json.dumps(value, sort_keys=True), dialect)

    def process_result_value(self, value: bytes | None, dialect: Dialect) -> Any:
        text = self._text.process_result_value(value, dialect)
        return None if text is None else json.loads(text)
