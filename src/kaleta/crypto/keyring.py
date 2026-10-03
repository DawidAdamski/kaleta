# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unlocked keys, in this process's memory only.

``KeyRing`` maps a session key (the browser's storage id) to what an unlock
produced: the account's data key and, for the owner, the member's private key
(kept because sealing the data key to a newcomer and re-keying need it).

Nothing here is ever written anywhere: not to ``app.storage.user`` (a file or
Redis), not to a log — ``__repr__`` of every object redacts its bytes. The
cost is deliberate and documented: a restart, or a second replica that did not
take the unlock, sees every session locked and asks for the passphrase again.

Entries expire after ``ttl_seconds`` (the session TTL), so a session the
browser abandoned does not keep its account's key in memory for ever.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from kaleta.config import settings
from kaleta.crypto.keys import (
    KdfParams,
    derive_index_key,
    derive_kek,
    generate_member_keys,
    new_salt,
    open_sealed,
    public_key_of,
    seal,
    unwrap_private_key,
    wrap_private_key,
)
from kaleta.crypto.recovery import normalise_recovery_code
from kaleta.exceptions import EncryptionError


@dataclass(frozen=True)
class DataKey:
    """An account's data key and the ``key_version`` its ciphertext header carries."""

    dek: bytes = field(repr=False)
    version: int = 1
    index_key: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.dek) != 32:
            msg = "A data key is 32 bytes."
            raise EncryptionError(msg)
        if not 0 <= self.version <= 255:
            msg = "A key version fits in one byte."
            raise EncryptionError(msg)
        object.__setattr__(self, "index_key", derive_index_key(self.dek))

    def __repr__(self) -> str:
        return f"DataKey(version={self.version}, dek=<redacted>)"


@dataclass(frozen=True)
class KeyMaterial:
    """One member's stored key block — the ``tenant_members`` / ``local_key_material`` columns.

    Everything here is safe for the operator to hold: the public key, salts,
    KDF parameters and three ciphertexts that only the passphrase, the
    recovery code or the private key can open.
    """

    public_key: bytes
    private_key_wrapped: bytes
    private_key_salt: bytes
    kdf_params: str
    dek_sealed: bytes | None
    recovery_wrapped: bytes | None = None
    recovery_salt: bytes | None = None

    def __repr__(self) -> str:
        return (
            f"KeyMaterial(public_key={self.public_key.hex()[:16]}…, "
            f"recovery={'yes' if self.recovery_wrapped else 'no'}, "
            f"dek_sealed={'yes' if self.dek_sealed else 'no'})"
        )

    @property
    def has_recovery(self) -> bool:
        return self.recovery_wrapped is not None and self.recovery_salt is not None


def create_key_material(
    passphrase: str,
    *,
    dek: bytes | None,
    recovery_code: str | None,
    params: KdfParams | None = None,
) -> tuple[KeyMaterial, bytes]:
    """A new keypair wrapped under ``passphrase`` (and the recovery code), plus its private key.

    ``dek`` is sealed to the new public key when given — the first member of a
    new account. An invited member gets theirs sealed later, by the owner.
    """
    params = params or KdfParams()
    keys = generate_member_keys()
    salt = new_salt()
    wrapped = wrap_private_key(keys.private_key, derive_kek(passphrase, salt, params))
    material = KeyMaterial(
        public_key=keys.public_key,
        private_key_wrapped=wrapped,
        private_key_salt=salt,
        kdf_params=params.to_json(),
        dek_sealed=seal(dek, keys.public_key) if dek is not None else None,
    )
    if recovery_code is not None:
        material = with_recovery_code(material, keys.private_key, recovery_code)
    return material, keys.private_key


def with_recovery_code(material: KeyMaterial, private_key: bytes, code: str) -> KeyMaterial:
    """``material`` with its recovery wrap replaced by one under ``code``."""
    params = KdfParams.from_json(material.kdf_params)
    salt = new_salt()
    kek = derive_kek(normalise_recovery_code(code), salt, params)
    return replace(
        material,
        recovery_wrapped=wrap_private_key(private_key, kek),
        recovery_salt=salt,
    )


def with_passphrase(material: KeyMaterial, private_key: bytes, passphrase: str) -> KeyMaterial:
    """``material`` re-wrapped under a new passphrase; recovery wrap and sealed DEK untouched."""
    params = KdfParams.from_json(material.kdf_params)
    salt = new_salt()
    return replace(
        material,
        private_key_wrapped=wrap_private_key(private_key, derive_kek(passphrase, salt, params)),
        private_key_salt=salt,
    )


def open_private_key(material: KeyMaterial, passphrase: str) -> bytes:
    """The private key ``passphrase`` unwraps — ``EncryptionError`` for a wrong one."""
    params = KdfParams.from_json(material.kdf_params)
    kek = derive_kek(passphrase, material.private_key_salt, params)
    private_key = unwrap_private_key(material.private_key_wrapped, kek)
    _check_pair(private_key, material)
    return private_key


def open_with_recovery(material: KeyMaterial, code: str) -> bytes:
    if material.recovery_wrapped is None or material.recovery_salt is None:
        msg = "No recovery code was set up for this key."
        raise EncryptionError(msg)
    params = KdfParams.from_json(material.kdf_params)
    kek = derive_kek(normalise_recovery_code(code), material.recovery_salt, params)
    try:
        private_key = unwrap_private_key(material.recovery_wrapped, kek)
    except EncryptionError as exc:
        msg = "That recovery code does not open this key."
        raise EncryptionError(msg) from exc
    _check_pair(private_key, material)
    return private_key


def open_data_key(material: KeyMaterial, private_key: bytes, version: int) -> DataKey:
    if material.dek_sealed is None:
        msg = "No data key has been sealed to this member yet."
        raise EncryptionError(msg)
    return DataKey(dek=open_sealed(material.dek_sealed, private_key), version=version)


def _check_pair(private_key: bytes, material: KeyMaterial) -> None:
    if public_key_of(private_key) != material.public_key:
        msg = "The stored keys do not belong together."
        raise EncryptionError(msg)


@dataclass(frozen=True)
class Unlocked:
    """What one unlocked session holds."""

    data_key: DataKey
    #: ``"tenant:<id>:user:<n>"`` or ``"local:<n>"`` — who unlocked, for
    #: ``lock_member`` and for bearer requests that ride on a member's unlock.
    member_ref: str
    private_key: bytes | None = field(default=None, repr=False)
    expires_at: float = 0.0

    def __repr__(self) -> str:
        return f"Unlocked(member_ref={self.member_ref!r}, data_key=<redacted>)"


class KeyRing:
    def __init__(
        self,
        ttl_seconds: Callable[[], float],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[str, Unlocked] = {}
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"KeyRing(sessions={self.count()})"

    def unlock(
        self,
        session_key: str,
        material: KeyMaterial,
        passphrase: str,
        *,
        member_ref: str,
        key_version: int,
        keep_private_key: bool = True,
    ) -> Unlocked:
        """Passphrase → KEK → private key → data key, held for ``session_key``."""
        private_key = open_private_key(material, passphrase)
        data_key = open_data_key(material, private_key, key_version)
        return self.put(
            session_key,
            data_key,
            member_ref=member_ref,
            private_key=private_key if keep_private_key else None,
        )

    def put(
        self,
        session_key: str,
        data_key: DataKey,
        *,
        member_ref: str,
        private_key: bytes | None = None,
    ) -> Unlocked:
        ttl = self._ttl()
        expires = self._clock() + ttl if ttl > 0 else float("inf")
        entry = Unlocked(
            data_key=data_key,
            member_ref=member_ref,
            private_key=private_key,
            expires_at=expires,
        )
        with self._lock:
            self._entries[session_key] = entry
        return entry

    def get(self, session_key: str | None) -> Unlocked | None:
        if session_key is None:
            return None
        with self._lock:
            entry = self._entries.get(session_key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[session_key]
                return None
            return entry

    def for_member(self, member_ref: str) -> Unlocked | None:
        """Any live unlock of ``member_ref`` — what a bearer request rides on."""
        now = self._clock()
        with self._lock:
            for key, entry in list(self._entries.items()):
                if entry.expires_at <= now:
                    del self._entries[key]
                    continue
                if entry.member_ref == member_ref:
                    return entry
        return None

    def lock(self, session_key: str | None) -> None:
        if session_key is None:
            return
        with self._lock:
            self._entries.pop(session_key, None)

    def lock_member(self, member_ref: str) -> int:
        """Drop every session ``member_ref`` unlocked; return how many."""
        with self._lock:
            keys = [k for k, e in self._entries.items() if e.member_ref == member_ref]
            for key in keys:
                del self._entries[key]
        return len(keys)

    def move(self, old_key: str, new_key: str) -> None:
        """Carry an unlock across a session-id rotation."""
        with self._lock:
            entry = self._entries.pop(old_key, None)
            if entry is not None:
                self._entries[new_key] = entry

    def count(self) -> int:
        now = self._clock()
        with self._lock:
            return sum(1 for e in self._entries.values() if e.expires_at > now)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def _session_ttl_seconds() -> float:
    return float(settings.session_ttl_hours) * 3600.0


#: The process's key ring.
key_ring = KeyRing(_session_ttl_seconds)
