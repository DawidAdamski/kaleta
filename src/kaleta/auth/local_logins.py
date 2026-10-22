# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acting on a local login across the registry and its family (ADR-38).

``LocalIdentityService`` only knows the registry. Disabling a login has to
reach further — into the family's schema and this process's key ring — so it
lives here, beside the other orchestration of the auth layer.
"""

from __future__ import annotations

import logging

from kaleta.auth.providers import get_auth_provider
from kaleta.auth.revocation_cache import revocation_cache
from kaleta.config import settings
from kaleta.crypto import key_ring, tenant_member_ref
from kaleta.db import AsyncSessionFactory
from kaleta.services.instance_admin_service import InstanceAdminService, RevokedMember

logger = logging.getLogger(__name__)


async def set_login_disabled(identity_id: int, disabled: bool, *, actor: str | None = None) -> None:
    """Refuse (or allow again) a login — and, when refusing, end what it holds now.

    Disabling raises the member's session watermark (every open browser
    session of theirs fails its next check), revokes their API tokens
    (``InstanceAdminService.set_disabled``, audited as ``actor``) and drops
    their unlocked key from this process's key ring. Another replica notices
    the watermark within its revocation cache's TTL; its key-ring entry goes
    when that session next fails the guard.
    """
    async with AsyncSessionFactory.public() as public:
        service = InstanceAdminService(
            public,
            actor=actor,
            auth_backend=settings.auth_backend,
            remover=get_auth_provider(),
        )
        revoked = await service.set_disabled(identity_id, disabled)
    if revoked is not None:
        locked = forget_revoked_member(revoked)
        logger.info(
            "Disabled local login %s: sessions and tokens revoked, %d unlocked key(s) dropped",
            identity_id,
            locked,
        )


def forget_revoked_member(revoked: RevokedMember) -> int:
    """Drop what *this process* holds for a member whose sessions were revoked.

    The cached revocation watermark and their unlocked key; returns how many
    unlocked keys went.
    """
    revocation_cache.forget(revoked.user_id, tenant_id=revoked.tenant_id)
    return key_ring.lock_member(tenant_member_ref(revoked.tenant_id, revoked.user_id))
