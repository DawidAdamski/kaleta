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

from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from kaleta.models.tenant import InstanceSetting, LocalIdentity
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.auth_service import MIN_PASSWORD_LENGTH

_REGISTRATION_KEY = "registration_mode"
_SUBJECT_PREFIX = "local:"
#: The same sentence for an unknown address and a wrong password.
_BAD_CREDENTIALS = "Invalid e-mail or password."


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
        must_change_password: bool = False,
    ) -> LocalIdentity:
        """A new login. ``ConflictError`` when the address is taken."""
        address = normalise_email(email)
        if "@" not in address or address.startswith("@") or address.endswith("@"):
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
            must_change_password=must_change_password,
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
        """
        if await self.is_empty():
            return await self.create(email, password, admin=True)
        if await self.registration_mode() is not RegistrationMode.OPEN:
            msg = "Sign-up is closed on this instance. Ask its administrator for an account."
            raise ValidationError(msg)
        return await self.create(email, password)

    async def authenticate(self, email: str, password: str) -> LocalIdentity:
        """The login for these credentials, or ``UnauthorizedError``."""
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

    async def set_password(
        self, identity_id: int, password: str, *, must_change: bool = False
    ) -> None:
        identity = await self._require(identity_id)
        self._validate_password(password)
        identity.password_hash = self._hasher.hash(password)
        identity.must_change_password = must_change
        await self.session.commit()

    async def set_disabled(self, identity_id: int, disabled: bool) -> None:
        identity = await self._require(identity_id)
        if disabled and identity.is_instance_admin and await self._admin_count() == 1:
            msg = "The last administrator cannot be disabled."
            raise ValidationError(msg)
        identity.disabled = disabled
        await self.session.commit()

    async def delete(self, identity_id: int) -> None:
        identity = await self.get(identity_id)
        if identity is None:
            return
        if identity.is_instance_admin and await self._admin_count() == 1:
            msg = "The last administrator cannot be deleted."
            raise ValidationError(msg)
        await self.session.delete(identity)
        await self.session.commit()

    # ── Internals ────────────────────────────────────────────────────────────

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
