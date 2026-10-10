# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data-passphrase gate between "signed in" and "can read the data".

With ``KALETA_ENCRYPTION=passphrase`` (every production instance) a signed-in
session still holds no key until its member types the data passphrase on
``/unlock``. The page guard sends every other page there while the session is
locked; the API answers ``423`` (``kaleta.api.deps``).

Views reach the ``KeyService`` through :func:`with_key_service`, which opens
the sessions the signed-in member's key block lives in — views may not open
database sessions themselves.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from urllib.parse import quote

from nicegui import app

from kaleta.auth.session import (
    SESSION_USER_ID,
    session_data_key,
    session_member_ref,
    session_tenant,
    storage_session_key,
)
from kaleta.config import settings
from kaleta.crypto import key_ring
from kaleta.db import AsyncSessionFactory
from kaleta.db.types import install_data_key_resolver
from kaleta.exceptions import UnauthorizedError
from kaleta.services.key_service import KeyService, TenantKeyStore
from kaleta.services.local_identity_service import LocalIdentityService, identity_id_of

UNLOCK_PATH = "/unlock"

#: Pages a signed-in but locked session may still open. Recovery with the
#: recovery code lives on ``/unlock`` itself rather than on Settings → Security
#: (as the plan first had it): the settings page renders every tab, and the
#: others read data a locked session cannot.
UNLOCK_EXEMPT_PATHS: frozenset[str] = frozenset({UNLOCK_PATH})


def install_unlock_resolver() -> None:
    """Let code that runs with no family context find the key this browser unlocked.

    A family's sessions carry it on the ``TenantContext``
    (``session_tenant_context``); this is the fallback for the rest.
    """
    if settings.encryption_enabled:
        install_data_key_resolver(session_data_key)


def unlock_redirect(path: str) -> str:
    return f"{UNLOCK_PATH}?redirect_to={quote(path, safe='/')}"


def current_session_key() -> str:
    key = storage_session_key()
    if key is None:
        msg = "No browser session to unlock."
        raise UnauthorizedError(msg)
    return key


def _signed_in_user_id() -> int:
    raw = app.storage.user.get(SESSION_USER_ID)
    if raw is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)
    return int(raw)


async def with_key_service[T](fn: Callable[[KeyService], Awaitable[T]]) -> T:
    """Run ``fn`` with the signed-in member's ``KeyService``."""
    user_id = _signed_in_user_id()
    async with AsyncExitStack() as stack:
        tenant = session_tenant()
        if tenant is None:
            msg = "Sign in first."
            raise UnauthorizedError(msg)
        data_session = await stack.enter_async_context(AsyncSessionFactory())
        public = await stack.enter_async_context(AsyncSessionFactory.public())
        store = TenantKeyStore(public, tenant.tenant_id, user_id)
        return await fn(KeyService(store, data_session))


async def is_login_password(passphrase: str) -> bool:
    """Whether ``passphrase`` is the signed-in member's login password.

    The plan's one rule beyond length: the data passphrase must not be the
    password, or whoever learns one has both. The password of a ``local``
    login is in ``public.local_identities``; a Supabase member's is held by
    the identity provider, so there is nothing to compare.
    """
    tenant = session_tenant()
    return tenant is not None and await is_local_login_password(tenant.auth_subject, passphrase)


async def is_local_login_password(subject: str, passphrase: str) -> bool:
    """Whether ``passphrase`` is the password of the ``local`` login ``subject``."""
    identity_id = identity_id_of(subject)
    if identity_id is None:
        return False
    async with AsyncSessionFactory.public() as public:
        return await LocalIdentityService(public).verify_password(identity_id, passphrase)


def lock_this_session() -> None:
    """Lock now: forget this browser's key; the next page asks for the passphrase."""
    key_ring.lock(storage_session_key())


def lock_member_everywhere() -> int:
    """Forget every unlock of the signed-in member (sign out everywhere)."""
    member_ref = session_member_ref()
    return key_ring.lock_member(member_ref) if member_ref is not None else 0
