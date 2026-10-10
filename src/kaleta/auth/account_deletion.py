# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings → Data → "Delete my account": the owner's GDPR path.

Here rather than in the view because it opens registry sessions, which views
may not. The view asks :func:`deletion_overview` whether to offer the button at
all — only the account's active owner gets one — and whom to list as losing
access; :func:`delete_signed_in_account` checks the data passphrase, removes
every member's identity, the schema and the registry rows, and forgets every
member's unlocked key. Signing the browser out is the view's last step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import session_tenant
from kaleta.auth.unlock import with_key_service
from kaleta.crypto import key_ring, tenant_member_ref
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import UnauthorizedError, ValidationError
from kaleta.services.account_deletion_service import (
    AccountDeletion,
    AccountDeletionService,
    AccountMember,
)
from kaleta.services.key_service import KeyService

logger = logging.getLogger(__name__)


class WrongPassphraseError(ValidationError):
    """The data passphrase did not open the key — nothing was deleted.

    Its own type so the dialog can say "wrong passphrase" for this alone, and
    not for a ``ValidationError`` the provider raises while removing identities
    (a missing service-role key, say).
    """


@dataclass(frozen=True)
class DeletionOverview:
    """Whether this session may delete its account, and who would lose access."""

    allowed: bool
    members: list[AccountMember]


async def deletion_overview() -> DeletionOverview:
    """Owner-only: anyone else sees no button."""
    tenant = session_tenant()
    if tenant is None:
        return DeletionOverview(allowed=False, members=[])
    async with AsyncSessionFactory.public() as public:
        service = AccountDeletionService(public, get_auth_provider())
        if not await service.is_owner(tenant.tenant_id, tenant.auth_subject):
            return DeletionOverview(allowed=False, members=[])
        return DeletionOverview(allowed=True, members=await service.members(tenant.tenant_id))


async def delete_signed_in_account(passphrase: str) -> AccountDeletion:
    """Delete the signed-in owner's account, once ``passphrase`` proves it is them.

    A wrong passphrase raises ``WrongPassphraseError`` before anything is touched;
    a session that is not the owner's raises ``UnauthorizedError``.
    """
    tenant = session_tenant()
    if tenant is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)

    async def _prove(service: KeyService) -> None:
        try:
            await service.open(passphrase)
        except ValidationError as exc:
            raise WrongPassphraseError(exc.message) from exc

    await with_key_service(_prove)
    async with AsyncSessionFactory.public() as public:
        service = AccountDeletionService(public, get_auth_provider())
        if not await service.is_owner(tenant.tenant_id, tenant.auth_subject):
            msg = "Only the account's owner can delete it."
            raise UnauthorizedError(msg)
        members = await service.members(tenant.tenant_id)
        deleted = await service.delete(tenant.tenant_id)
    for member in members:
        if member.user_id is not None:
            key_ring.lock_member(tenant_member_ref(tenant.tenant_id, member.user_id))
    logger.info(
        "Account %s deleted by its owner (%d identities)",
        deleted.tenant_id,
        deleted.identities_removed,
    )
    return deleted
