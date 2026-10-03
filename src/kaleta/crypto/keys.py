# SPDX-License-Identifier: AGPL-3.0-or-later
"""The key hierarchy: passphrase → KEK → member private key → sealed data key.

Every primitive comes from ``cryptography`` (AES-256-GCM, X25519, HKDF-SHA256)
and ``argon2-cffi`` (Argon2id). Nothing here is home-made beyond the way they
are put together, and that is the standard construction:

* **wrap** — AES-256-GCM under a 32-byte KEK, a 12-byte random nonce, and an
  AAD naming what is wrapped, so a wrapped private key cannot be passed off
  as anything else;
* **seal** — an anonymous sealed box: an ephemeral X25519 key agrees a secret
  with the recipient's public key, HKDF-SHA256 turns it into an AES key (salted
  with both public keys), AES-256-GCM encrypts. Only the recipient's private
  key opens it, and the sender keeps nothing.

Failures are ``EncryptionError``: a wrong passphrase, a damaged blob and a
blob sealed to somebody else all look the same from outside, on purpose.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from kaleta.exceptions import EncryptionError

KEY_BYTES = 32
NONCE_BYTES = 12
SALT_BYTES = 16
#: Version byte in front of every wrapped or sealed blob, so the layout can
#: change without guessing.
_BLOB_V1 = 0x01
_WRAP_AAD = b"kaleta-member-private-key-v1"
_SEAL_INFO = b"kaleta-sealed-box-v1"
_INDEX_INFO = b"kaleta-blind-index"


@dataclass(frozen=True)
class KdfParams:
    """Argon2id cost, stored per member so it can be raised later.

    ``memory_kib`` 65 536 is the plan's 64 MiB. Unlocks are serialised by the
    ``KeyService`` (see its docstring), so a burst of logins costs time, not
    memory.
    """

    time_cost: int = 3
    memory_kib: int = 64 * 1024
    parallelism: int = 1

    def to_json(self) -> str:
        return json.dumps(
            {
                "alg": "argon2id",
                "t": self.time_cost,
                "m": self.memory_kib,
                "p": self.parallelism,
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str | None) -> KdfParams:
        if not raw:
            msg = "No key-derivation parameters are stored for this member."
            raise EncryptionError(msg)
        try:
            data = json.loads(raw)
            if data.get("alg") != "argon2id":
                raise ValueError(data.get("alg"))
            return cls(
                time_cost=int(data["t"]),
                memory_kib=int(data["m"]),
                parallelism=int(data["p"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            msg = "The stored key-derivation parameters are not readable."
            raise EncryptionError(msg) from exc


@dataclass(frozen=True)
class MemberKeys:
    """A freshly generated keypair. ``private_key`` is raw bytes — never stored as is."""

    private_key: bytes
    public_key: bytes

    def __repr__(self) -> str:
        return f"MemberKeys(public_key={self.public_key.hex()[:16]}…, private_key=<redacted>)"


def new_salt() -> bytes:
    return os.urandom(SALT_BYTES)


def derive_kek(secret: str, salt: bytes, params: KdfParams) -> bytes:
    """A 32-byte key-encryption key from a passphrase (or recovery code)."""
    if len(salt) < SALT_BYTES:
        msg = "The key-derivation salt is too short."
        raise EncryptionError(msg)
    return hash_secret_raw(
        secret=secret.encode("utf-8"),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def generate_member_keys() -> MemberKeys:
    private = X25519PrivateKey.generate()
    return MemberKeys(
        private_key=private.private_bytes_raw(),
        public_key=private.public_key().public_bytes_raw(),
    )


def public_key_of(private_key: bytes) -> bytes:
    return X25519PrivateKey.from_private_bytes(private_key).public_key().public_bytes_raw()


def generate_dek() -> bytes:
    return os.urandom(KEY_BYTES)


def wrap_private_key(private_key: bytes, kek: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return bytes([_BLOB_V1]) + nonce + AESGCM(kek).encrypt(nonce, private_key, _WRAP_AAD)


def unwrap_private_key(wrapped: bytes, kek: bytes) -> bytes:
    """The private key, or ``EncryptionError`` for a wrong KEK or a damaged blob."""
    if len(wrapped) < 1 + NONCE_BYTES + KEY_BYTES or wrapped[0] != _BLOB_V1:
        msg = "The wrapped key is not in a format this version reads."
        raise EncryptionError(msg)
    nonce, body = wrapped[1 : 1 + NONCE_BYTES], wrapped[1 + NONCE_BYTES :]
    try:
        return AESGCM(kek).decrypt(nonce, body, _WRAP_AAD)
    except InvalidTag as exc:
        msg = "That passphrase does not open this key."
        raise EncryptionError(msg) from exc


def _box_key(shared: bytes, ephemeral_public: bytes, recipient_public: bytes) -> bytes:
    return HKDF(
        algorithm=SHA256(),
        length=KEY_BYTES,
        salt=ephemeral_public + recipient_public,
        info=_SEAL_INFO,
    ).derive(shared)


def seal(plaintext: bytes, recipient_public_key: bytes) -> bytes:
    """Encrypt ``plaintext`` so that only the holder of the matching private key can read it."""
    recipient = X25519PublicKey.from_public_bytes(recipient_public_key)
    ephemeral = X25519PrivateKey.generate()
    ephemeral_public = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    key = _box_key(ephemeral.exchange(recipient), ephemeral_public, recipient_public_key)
    nonce = os.urandom(NONCE_BYTES)
    return (
        bytes([_BLOB_V1])
        + ephemeral_public
        + nonce
        + AESGCM(key).encrypt(nonce, plaintext, recipient_public_key)
    )


def open_sealed(sealed: bytes, private_key: bytes) -> bytes:
    """Open a sealed box; ``EncryptionError`` when it was sealed to someone else."""
    if len(sealed) < 1 + KEY_BYTES + NONCE_BYTES + 16 or sealed[0] != _BLOB_V1:
        msg = "The sealed key is not in a format this version reads."
        raise EncryptionError(msg)
    ephemeral_public = sealed[1 : 1 + KEY_BYTES]
    nonce = sealed[1 + KEY_BYTES : 1 + KEY_BYTES + NONCE_BYTES]
    body = sealed[1 + KEY_BYTES + NONCE_BYTES :]
    private = X25519PrivateKey.from_private_bytes(private_key)
    recipient_public = private.public_key().public_bytes_raw()
    shared = private.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
    key = _box_key(shared, ephemeral_public, recipient_public)
    try:
        return AESGCM(key).decrypt(nonce, body, recipient_public)
    except InvalidTag as exc:
        msg = "This data key was not sealed to this member."
        raise EncryptionError(msg) from exc


def derive_index_key(dek: bytes) -> bytes:
    """The blind-index key: HKDF of the DEK, so it is never stored anywhere."""
    return HKDF(algorithm=SHA256(), length=KEY_BYTES, salt=None, info=_INDEX_INFO).derive(dek)
