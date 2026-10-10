# SPDX-License-Identifier: AGPL-3.0-or-later
"""Acting on a local login across the registry and its family (ADR-38).

``LocalIdentityService`` only knows the registry. Disabling a login has to
reach further — into the family's schema and this process's key ring — so it
lives here, beside the other orchestration of the auth layer.
"""

from __future__ import annotations

import logging

from kaleta.auth.revocation_cache import revocation_cache
from kaleta.crypto import key_ring, tenant_member_ref
from kaleta.db import AsyncSessionFactory
from kaleta.db.tenant_context import use_tenant
from kaleta.services import ApiTokenService, AuthService, TenantService
from kaleta.services.local_identity_service import LocalIdentityService, subject_of

logger = logging.getLogger(__name__)


async def set_login_disabled(identity_id: int, disabled: bool) -> None:
    """Refuse (or allow again) a login — and, when refusing, end what it holds now.

    Disabling raises the member's session watermark (every open browser
    session of theirs fails its next check), revokes their API tokens and
    drops their unlocked key from this process's key ring. Another replica
    notices the watermark within its revocation cache's TTL; its key-ring
    entry goes when that session next fails the guard.
    """
    async with AsyncSessionFactory.public() as public:
        await LocalIdentityService(public).set_disabled(identity_id, disabled)
        membership = await TenantService(public).get_member_by_subject(subject_of(identity_id))
    if not disabled or membership is None or membership.member.user_id is None:
        return
    user_id = membership.member.user_id
    with use_tenant(membership.context()):
        async with AsyncSessionFactory() as session:
            await AuthService(session).revoke_sessions(user_id)
            revoked = await ApiTokenService(session).revoke_all(user_id=user_id)
        revocation_cache.forget(user_id)
    locked = key_ring.lock_member(tenant_member_ref(membership.tenant.id, user_id))
    logger.info(
        "Disabled local login %s: sessions revoked, %d token(s), %d unlocked key(s) dropped",
        identity_id,
        revoked,
        locked,
    )
