# SPDX-License-Identifier: AGPL-3.0-or-later
"""The signed-in member acting in their household (``hosted-household-sharing``).

Views reach ``HouseholdService`` through here: it opens the registry session,
finds the member by the session's identity, and hands over the key this
browser unlocked. After a member loses access — removed, or leaving — this is
also where *this process* forgets them (``forget_revoked_member``), which the
service cannot do: the revocation cache and the key ring of a browser session
belong to the auth layer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from kaleta.auth.local_logins import forget_revoked_member
from kaleta.auth.session import session_data_key, session_tenant
from kaleta.auth.unlock import current_session_key, with_key_service
from kaleta.config import settings
from kaleta.crypto import key_ring
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import ConflictError, NotFoundError, UnauthorizedError
from kaleta.services.household_service import (
    HouseholdInvitations,
    HouseholdService,
    InvitationPreview,
    RemovedMember,
)
from kaleta.services.instance_admin_service import RevokedMember
from kaleta.services.key_service import KeyService


async def with_household[T](fn: Callable[[HouseholdService], Awaitable[T]]) -> T:
    """Run ``fn`` with the signed-in member's ``HouseholdService``."""
    tenant = session_tenant()
    if tenant is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)
    async with AsyncSessionFactory.public() as public:
        service = await HouseholdService.for_subject(public, tenant.auth_subject)
        return await fn(service)


async def preview_invitation(token: str) -> InvitationPreview | None:
    """The invitation ``token`` stands for; ``None`` when used, replaced, expired or unknown."""
    try:
        async with AsyncSessionFactory.public() as public:
            return await HouseholdInvitations(public).preview(token)
    except (NotFoundError, ConflictError):
        return None


async def accept_invitation(token: str, password: str) -> str:
    """``local`` logins: create the invited address's login; return the address."""
    async with AsyncSessionFactory.public() as public:
        return await HouseholdInvitations(public).accept_with_password(token, password)


def household_is_rekeying() -> bool:
    """The signed-in member's household is frozen for a re-key in this process."""
    tenant = session_tenant()
    return tenant is not None and key_ring.is_frozen(tenant.tenant_id)


async def approve_member(member_id: int, passphrase: str, shown_fingerprint: str | None) -> None:
    """Seal the household's key to a pending member, after the owner typed the passphrase.

    The passphrase opens the key afresh (a wrong one is a ``ValidationError``)
    — the deliberate moment of sealing, not just a session that happens to be
    unlocked. ``shown_fingerprint`` is the one the dialog showed. With
    encryption off there is no key to seal and no passphrase to ask for.
    """
    if settings.encryption_enabled:
        session_key = current_session_key()

        async def _open(service: KeyService) -> None:
            await service.unlock(session_key, passphrase)

        await with_key_service(_open)
    key = session_data_key()

    async def _approve(service: HouseholdService) -> None:
        await service.approve(member_id, key, expected_fingerprint=shown_fingerprint)

    await with_household(_approve)


async def remove_member(member_id: int, *, rekey: bool) -> RemovedMember:
    key = session_data_key()

    async def _remove(service: HouseholdService) -> RemovedMember:
        return await service.remove(member_id, key, rekey=rekey)

    return _forgotten(await with_household(_remove))


async def leave_household() -> RemovedMember:
    """The signed-in member leaves, re-keying behind them; the caller signs them out."""
    key = session_data_key()

    async def _leave(service: HouseholdService) -> RemovedMember:
        return await service.leave(key)

    return _forgotten(await with_household(_leave))


async def reset_my_keys() -> None:
    async def _reset(service: HouseholdService) -> None:
        await service.reset_keys()

    await with_household(_reset)


def _forgotten(removed: RemovedMember) -> RemovedMember:
    forget_revoked_member(RevokedMember(tenant_id=removed.tenant_id, user_id=removed.user_id))
    return removed
