# SPDX-License-Identifier: AGPL-3.0-or-later
"""Logins of ``KALETA_AUTH_BACKEND=local`` kept in the registry (ADR-38).

Works on a session with no tenant schema (``AsyncSessionFactory.public()``):
``public.local_identities`` holds an e-mail, an argon2id hash and two flags
per login, ``public.instance_settings`` the instance's registration mode. The
first login created on an empty instance is its administrator.

The family a login belongs to is not here: that is
``tenant_members.auth_subject`` = ``local:<id>``, filled by
``TenantService.provision`` at the first sign-in, exactly as for Supabase.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from kaleta.models.tenant import InstanceSetting, LocalIdentity
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.auth_service import MIN_PASSWORD_LENGTH

_REGISTRATION_KEY = "registration_mode"
_SUBJECT_PREFIX = "local:"
#: The same sentence for an unknown address and a wrong password.
_BAD_CREDENTIALS = "Invalid e-mail or password."
#: Longer input is refused before hashing: argon2 of a multi-megabyte string
#: is a way to make the server work, not a password.
MAX_PASSWORD_LENGTH = 1024
#: ``pg_advisory_xact_lock`` key for "who is an administrator" decisions.
_ADMIN_LOCK_KEY = 0x4B414C4554410001  # "KALETA" + 1
#: The same, within one process (and the only guard on SQLite).
_admin_lock = asyncio.Lock()


def subject_of(identity_id: int) -> str:
    return f"{_SUBJECT_PREFIX}{identity_id}"


def identity_id_of(subject: str) -> int | None:
    """The ``local_identities.id`` behind a subject, or ``None`` for another provider's."""
    if not subject.startswith(_SUBJECT_PREFIX):
        return None
    try:
        return int(subject.removeprefix(_SUBJECT_PREFIX))
    except ValueError:
        return None


def normalise_email(email: str) -> str:
    return email.strip().lower()


class LocalIdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._hasher = PasswordHasher()

    # ── Instance ─────────────────────────────────────────────────────────────

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(LocalIdentity))
        return int(result.scalar_one())

    async def is_empty(self) -> bool:
        """No login exists yet: the next sign-up creates the administrator."""
        return await self.count() == 0

    async def registration_mode(self) -> RegistrationMode:
        row = await self.session.get(InstanceSetting, _REGISTRATION_KEY)
        if row is None:
            return RegistrationMode.CLOSED
        try:
            return RegistrationMode(row.value)
        except ValueError:
            return RegistrationMode.CLOSED

    async def set_registration_mode(self, mode: RegistrationMode) -> None:
        row = await self.session.get(InstanceSetting, _REGISTRATION_KEY)
        if row is None:
            self.session.add(InstanceSetting(key=_REGISTRATION_KEY, value=mode.value))
        else:
            row.value = mode.value
        await self.session.commit()

    # ── Logins ───────────────────────────────────────────────────────────────

    async def get(self, identity_id: int) -> LocalIdentity | None:
        return await self.session.get(LocalIdentity, identity_id)

    async def get_by_email(self, email: str) -> LocalIdentity | None:
        result = await self.session.execute(
            select(LocalIdentity).where(LocalIdentity.email == normalise_email(email))
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[LocalIdentity]:
        result = await self.session.execute(select(LocalIdentity).order_by(LocalIdentity.id))
        return list(result.scalars().all())

    async def create(
        self,
        email: str,
        password: str,
        *,
        admin: bool = False,
    ) -> LocalIdentity:
        """A new login. ``ConflictError`` when the address is taken."""
        address = normalise_email(email)
        local, _, domain = address.partition("@")
        if not local or not domain or "@" in domain or any(c.isspace() for c in address):
            msg = "Enter an e-mail address."
            raise ValidationError(msg)
        self._validate_password(password)
        if await self.get_by_email(address) is not None:
            msg = "An account with this e-mail address already exists."
            raise ConflictError(msg)
        identity = LocalIdentity(
            email=address,
            password_hash=self._hasher.hash(password),
            is_instance_admin=admin,
        )
        self.session.add(identity)
        await self.session.commit()
        await self.session.refresh(identity)
        return identity

    async def sign_up(self, email: str, password: str) -> LocalIdentity:
        """Self-service sign-up: the first login of an instance, or ``open`` mode.

        The first login becomes the instance administrator. Afterwards sign-up
        needs ``RegistrationMode.OPEN``; ``closed`` and ``invite`` refuse it
        with a sentence (the invitation path is ``hosted-household-sharing``'s).

        "Is the instance empty" and the insert run under one lock, so two
        first sign-ups racing each other yield one administrator: the second
        finds a login and meets the (closed) registration mode.
        """
        async with self._admin_decision():
            if await self.is_empty():
                return await self.create(email, password, admin=True)
            if await self.registration_mode() is not RegistrationMode.OPEN:
                msg = "Sign-up is closed on this instance. Ask its administrator for an account."
                raise ValidationError(msg)
            return await self.create(email, password)

    async def authenticate(self, email: str, password: str) -> LocalIdentity:
        """The login for these credentials, or ``UnauthorizedError``."""
        if len(password) > MAX_PASSWORD_LENGTH:
            raise UnauthorizedError(_BAD_CREDENTIALS)
        identity = await self.get_by_email(email)
        if identity is None:
            # Hash anyway, so an unknown address costs what a known one does.
            self._hasher.hash(password)
            raise UnauthorizedError(_BAD_CREDENTIALS)
        if not self._matches(identity.password_hash, password) or identity.disabled:
            raise UnauthorizedError(_BAD_CREDENTIALS)
        identity.last_login_at = datetime.now(UTC)
        await self.session.commit()
        return identity

    async def verify_password(self, identity_id: int, password: str) -> bool:
        identity = await self.get(identity_id)
        return identity is not None and self._matches(identity.password_hash, password)

    async def set_password(self, identity_id: int, password: str) -> None:
        identity = await self._require(identity_id)
        self._validate_password(password)
        identity.password_hash = self._hasher.hash(password)
        await self.session.commit()

    async def set_disabled(self, identity_id: int, disabled: bool) -> None:
        """Refuse or allow this login's sign-ins.

        Only the sign-in: a disabled login's open sessions, API tokens and
        unlocked key are ended by ``kaleta.auth.local_logins.set_login_disabled``,
        which calls this and then reaches into the login's family.
        """
        async with self._admin_decision():
            identity = await self._require(identity_id)
            if (
                disabled
                and identity.is_instance_admin
                and not identity.disabled
                and await self._admin_count() == 1
            ):
                msg = "The last administrator cannot be disabled."
                raise ValidationError(msg)
            identity.disabled = disabled
            await self.session.commit()

    async def delete(self, identity_id: int) -> None:
        async with self._admin_decision():
            identity = await self.get(identity_id)
            if identity is None:
                return
            if (
                identity.is_instance_admin
                and not identity.disabled
                and await self._admin_count() == 1
            ):
                msg = "The last administrator cannot be deleted."
                raise ValidationError(msg)
            await self.session.delete(identity)
            await self.session.commit()

    # ── Internals ────────────────────────────────────────────────────────────

    @asynccontextmanager
    async def _admin_decision(self) -> AsyncIterator[None]:
        """Serialise decisions about who is an administrator.

        In-process with an ``asyncio.Lock``; across processes with a
        transaction-level advisory lock on Postgres, released by the commit (or
        rollback) that ends the decision.
        """
        async with _admin_lock:
            bind = self.session.bind
            if bind is not None and bind.dialect.name == "postgresql":
                await self.session.execute(
                    text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADMIN_LOCK_KEY}
                )
            try:
                yield
            except BaseException:
                # A refused decision commits nothing; ending the transaction
                # also releases the advisory lock.
                await self.session.rollback()
                raise

    async def _require(self, identity_id: int) -> LocalIdentity:
        identity = await self.get(identity_id)
        if identity is None:
            msg = "No such login."
            raise NotFoundError(msg)
        return identity

    async def _admin_count(self) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(LocalIdentity)
            .where(LocalIdentity.is_instance_admin.is_(True), LocalIdentity.disabled.is_(False))
        )
        return int(result.scalar_one())

    def _matches(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            msg = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            raise ValidationError(msg)
        if len(password) > MAX_PASSWORD_LENGTH:
            msg = f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
            raise ValidationError(msg)
