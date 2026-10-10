# SPDX-License-Identifier: AGPL-3.0-or-later
"""A member's data passphrase: set it up, unlock with it, change it, recover it.

``kaleta.crypto`` turns bytes into bytes; this service reads and writes the
stored key block and puts what an unlock opens into the process's
``key_ring``. The key block is the member's ``public.tenant_members`` row
(:class:`TenantKeyStore`); the flows are written against :class:`KeyStore`,
the five questions any store answers.

Argon2id at 64 MiB is what makes a guessed passphrase expensive, and also what
makes a burst of unlocks expensive for a small host: every derivation runs in
a worker thread (it would otherwise stall the event loop for the whole
derivation) behind a process-wide lock, so N simultaneous unlocks cost N × the
time of one, never N × 64 MiB. A ``threading.Lock`` taken in the worker, not
an ``asyncio.Semaphore``: the latter binds to the first event loop that waits
on it.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.crypto import (
    DataKey,
    KdfParams,
    KeyMaterial,
    Unlocked,
    create_key_material,
    generate_dek,
    key_ring,
    new_recovery_code,
    open_data_key,
    open_private_key,
    open_with_recovery,
    tenant_member_ref,
    with_passphrase,
    with_recovery_code,
)
from kaleta.db.types import use_data_key
from kaleta.exceptions import ConflictError, EncryptionError, NotFoundError, ValidationError
from kaleta.models.tenant import Tenant, TenantMember
from kaleta.services.data_encryption_service import DataEncryptionService

log = logging.getLogger(__name__)

#: The plan's floor; a strength meter is out of scope.
PASSPHRASE_MIN_LENGTH = 12

#: One derivation at a time, process-wide — see the module docstring.
_derivations = threading.Lock()

KeyStatus = Literal["setup_required", "awaiting_key", "ready"]


def _serialised[T](fn: Callable[[], T]) -> T:
    with _derivations:
        return fn()


async def _derive[T](fn: Callable[[], T]) -> T:
    """Run a KDF-bound ``fn`` in a worker thread, one at a time."""
    return await asyncio.to_thread(_serialised, fn)


class KeyStore(Protocol):
    """Where one member's key block is kept."""

    member_ref: str

    async def load(self) -> KeyMaterial | None: ...

    async def save(self, material: KeyMaterial) -> None: ...

    async def key_version(self) -> int: ...

    async def others_hold_a_key(self) -> bool:
        """Whether another member of the same account already has the data key sealed."""
        ...


class TenantKeyStore:
    """``public.tenant_members``. ``session`` is a public one (or any that reaches ``public``)."""

    def __init__(self, session: AsyncSession, tenant_id: int, user_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.member_ref = tenant_member_ref(tenant_id, user_id)

    async def _member(self) -> TenantMember:
        result = await self.session.execute(
            select(TenantMember).where(
                TenantMember.tenant_id == self.tenant_id, TenantMember.user_id == self.user_id
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            msg = "This sign-in has no membership in the account."
            raise NotFoundError(msg)
        return member

    async def load(self) -> KeyMaterial | None:
        m = await self._member()
        if (
            m.public_key is None
            or m.private_key_wrapped is None
            or m.private_key_salt is None
            or m.kdf_params is None
        ):
            return None
        return KeyMaterial(
            public_key=m.public_key,
            private_key_wrapped=m.private_key_wrapped,
            private_key_salt=m.private_key_salt,
            kdf_params=m.kdf_params,
            dek_sealed=m.dek_sealed,
            recovery_wrapped=m.recovery_wrapped,
            recovery_salt=m.recovery_salt,
        )

    async def save(self, material: KeyMaterial) -> None:
        m = await self._member()
        m.public_key = material.public_key
        m.private_key_wrapped = material.private_key_wrapped
        m.private_key_salt = material.private_key_salt
        m.kdf_params = material.kdf_params
        m.dek_sealed = material.dek_sealed
        m.recovery_wrapped = material.recovery_wrapped
        m.recovery_salt = material.recovery_salt
        await self.session.commit()

    async def key_version(self) -> int:
        tenant = await self.session.get(Tenant, self.tenant_id)
        return tenant.key_version if tenant is not None else 1

    async def others_hold_a_key(self) -> bool:
        result = await self.session.execute(
            select(TenantMember.id).where(
                TenantMember.tenant_id == self.tenant_id,
                TenantMember.user_id != self.user_id,
                TenantMember.dek_sealed.is_not(None),
            )
        )
        return result.first() is not None


@dataclass(frozen=True)
class KeySetup:
    """What a first set-up hands back: the code to show once, and the open key."""

    recovery_code: str
    data_key: DataKey | None


class KeyService:
    """One member's passphrase flows over a :class:`KeyStore`.

    ``data_session`` is the session on the family's own data (its schema): a
    first set-up rewrites what is already there under the new key.
    """

    def __init__(
        self, store: KeyStore, data_session: AsyncSession, *, params: KdfParams | None = None
    ) -> None:
        """``params``: the Argon2id cost a *new* key block is wrapped under.

        Stored with the block, so changing the default later only affects
        set-ups from then on; every other flow reads the block's own.
        """
        self.store = store
        self.data_session = data_session
        self.params = params or KdfParams()

    # ── Status ───────────────────────────────────────────────────────────────

    async def status(self) -> KeyStatus:
        material = await self.store.load()
        if material is None:
            return "setup_required"
        if material.dek_sealed is None:
            # An invited member: the owner seals the key to them on approval
            # (hosted-household-sharing §2).
            return "awaiting_key"
        return "ready"

    async def has_recovery(self) -> bool:
        material = await self.store.load()
        return material is not None and material.has_recovery

    # ── Set up ───────────────────────────────────────────────────────────────

    @staticmethod
    def validate_passphrase(passphrase: str, *, login_password_matches: bool = False) -> None:
        if len(passphrase) < PASSPHRASE_MIN_LENGTH:
            msg = f"Choose a data passphrase of at least {PASSPHRASE_MIN_LENGTH} characters."
            raise ValidationError(msg)
        if login_password_matches:
            msg = "Choose a data passphrase that is not your login password."
            raise ValidationError(msg)

    async def setup(
        self,
        session_key: str | None,
        passphrase: str,
        *,
        login_password_matches: bool = False,
    ) -> KeySetup:
        """Create this member's keypair and recovery code; unlock ``session_key``.

        The first member of an account also creates the data key, and the
        data already in the account (an upgraded database, a hosted account
        from before encryption) is rewritten under it. A later member gets a
        keypair only and waits for the data key to be sealed to it.
        """
        self.validate_passphrase(passphrase, login_password_matches=login_password_matches)
        if await self.store.load() is not None:
            msg = "A data passphrase is already set up for this account."
            raise ConflictError(msg)
        first = not await self.store.others_hold_a_key()
        dek = generate_dek() if first else None
        code = new_recovery_code()
        material, private_key = await _derive(
            partial(
                create_key_material, passphrase, dek=dek, recovery_code=code, params=self.params
            )
        )
        data_key: DataKey | None = None
        if dek is not None:
            data_key = DataKey(dek, version=await self.store.key_version())
            await self._encrypt_existing_data(data_key)
        await self.store.save(material)
        if data_key is not None and session_key is not None:
            key_ring.put(
                session_key, data_key, member_ref=self.store.member_ref, private_key=private_key
            )
        log.info("Data passphrase set up for %s", self.store.member_ref)
        return KeySetup(recovery_code=code, data_key=data_key)

    async def _encrypt_existing_data(self, data_key: DataKey) -> None:
        """Rewrite the account's rows under its new key, before the key is stored.

        Committed before the key block: a crash in between leaves rows no key
        opens — but the same crash the other way round would leave a key whose
        account still holds plaintext *and* plaintext-key indexes, which every
        lookup would then miss. Neither is recoverable without the backup the
        operator takes first; the order chosen fails loudly (nothing unlocks)
        rather than quietly (duplicates).
        """
        with use_data_key(data_key):
            counts = await DataEncryptionService(self.data_session).rewrite_all()
            await self.data_session.commit()
        if any(counts.values()):
            log.info("Encrypted the existing data: %s", counts)

    # ── Unlock and lock ──────────────────────────────────────────────────────

    async def _material(self) -> KeyMaterial:
        material = await self.store.load()
        if material is None:
            msg = "No data passphrase is set up yet."
            raise NotFoundError(msg)
        return material

    async def open(self, passphrase: str) -> tuple[DataKey, bytes]:
        """The data key and private key ``passphrase`` opens — nothing is kept."""
        material = await self._material()
        if material.dek_sealed is None:
            msg = "Your data key has not been shared with you yet."
            raise ConflictError(msg)
        version = await self.store.key_version()
        try:
            private_key = await _derive(partial(open_private_key, material, passphrase))
        except EncryptionError as exc:
            msg = "That passphrase does not unlock your data."
            raise ValidationError(msg) from exc
        return open_data_key(material, private_key, version), private_key

    async def unlock(self, session_key: str, passphrase: str) -> Unlocked:
        data_key, private_key = await self.open(passphrase)
        return key_ring.put(
            session_key, data_key, member_ref=self.store.member_ref, private_key=private_key
        )

    @staticmethod
    def lock(session_key: str | None) -> None:
        key_ring.lock(session_key)

    # ── Change and recover ───────────────────────────────────────────────────

    async def change_passphrase(self, current: str, new: str) -> None:
        """Re-wrap the private key; the recovery wrap and the sealed key stay as they are."""
        self.validate_passphrase(new)
        material = await self._material()
        try:
            private_key = await _derive(partial(open_private_key, material, current))
        except EncryptionError as exc:
            msg = "That is not your current data passphrase."
            raise ValidationError(msg) from exc
        updated = await _derive(partial(with_passphrase, material, private_key, new))
        await self.store.save(updated)

    async def regenerate_recovery_code(self, passphrase: str) -> str:
        """A new recovery code; the old one stops working."""
        material = await self._material()
        try:
            private_key = await _derive(partial(open_private_key, material, passphrase))
        except EncryptionError as exc:
            msg = "That passphrase does not unlock your data."
            raise ValidationError(msg) from exc
        code = new_recovery_code()
        await self.store.save(
            await _derive(partial(with_recovery_code, material, private_key, code))
        )
        return code

    async def recover(self, session_key: str, code: str, new_passphrase: str) -> str:
        """Open with the recovery code, set ``new_passphrase``, unlock; return a new code.

        The code that was just typed in is replaced: it has been seen on this
        screen, and a code that was used once is no longer only on paper.
        """
        self.validate_passphrase(new_passphrase)
        material = await self._material()
        try:
            private_key = await _derive(partial(open_with_recovery, material, code))
        except EncryptionError as exc:
            msg = "That recovery code does not open your data."
            raise ValidationError(msg) from exc
        fresh = new_recovery_code()
        updated = await _derive(partial(with_passphrase, material, private_key, new_passphrase))
        updated = await _derive(partial(with_recovery_code, updated, private_key, fresh))
        await self.store.save(updated)
        if updated.dek_sealed is not None:
            data_key = open_data_key(updated, private_key, await self.store.key_version())
            key_ring.put(
                session_key, data_key, member_ref=self.store.member_ref, private_key=private_key
            )
        return fresh


async def open_family_data_key(
    public: AsyncSession, data_session: AsyncSession, tenant_id: int, passphrase: str
) -> DataKey:
    """The data key any member of family ``tenant_id``'s ``passphrase`` opens — for scripts.

    ``scripts/seed.py`` and ``scripts/reset_demo.py`` run without a browser
    session; they are given the passphrase (``KALETA_DATA_PASSPHRASE`` or a
    prompt) and work under the key it opens.
    """
    holders = (
        (
            await public.execute(
                select(TenantMember.user_id).where(
                    TenantMember.tenant_id == tenant_id,
                    TenantMember.user_id.is_not(None),
                    TenantMember.dek_sealed.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not holders:
        msg = (
            "No data passphrase is set up in this family yet. Sign in once and "
            "choose one, or run with KALETA_DEBUG=true KALETA_ENCRYPTION=off."
        )
        raise NotFoundError(msg)
    for user_id in holders:
        if user_id is None:
            continue
        service = KeyService(TenantKeyStore(public, tenant_id, user_id), data_session)
        try:
            data_key, _private_key = await service.open(passphrase)
        except (ValidationError, ConflictError):
            continue
        return data_key
    msg = "That passphrase does not unlock this family's data."
    raise ValidationError(msg)
