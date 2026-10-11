# SPDX-License-Identifier: AGPL-3.0-or-later
"""The instance administrator's session: who may open ``/admin``, the step-up,
and the password an administrator set that its owner must replace.

Views may not open database sessions, so ``/admin`` and ``/change-password``
reach ``InstanceAdminService`` and ``LocalIdentityService`` through here.

- :func:`stamp_login_flags` runs once per sign-in (the session rotation): it
  records whether the login administers the instance (the navigation's hint)
  and whether its password must be changed (the page guard's rule).
- :func:`with_admin_service` asks the registry again on every call; anyone
  else gets ``NotFoundError``.
- Every action on ``/admin`` needs the password proved within the last
  :data:`ADMIN_STEP_UP_MINUTES` (and a code, when the administrator has two-factor
  sign-in on): :func:`admin_step_up_needed`, :func:`prove_admin`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from nicegui import app

from kaleta.auth.local_logins import forget_revoked_member
from kaleta.auth.login_rate_limit import mfa_rate_limiter
from kaleta.auth.providers import get_auth_provider
from kaleta.auth.session import (
    SESSION_USER_ID,
    admin_step_up_within,
    clear_password_set_by_admin,
    is_instance_admin_session,
    mark_admin_step_up,
    password_set_by_admin,
    session_tenant,
    stamp_admin_flags,
)
from kaleta.config import settings
from kaleta.db import AsyncSessionFactory
from kaleta.exceptions import NotFoundError, UnauthorizedError, ValidationError
from kaleta.schemas.identity import Identity
from kaleta.services import HostedMfaService, MfaService
from kaleta.services.instance_admin_service import InstanceAdminService, is_instance_admin
from kaleta.services.local_identity_service import LocalIdentityService, identity_id_of

ADMIN_PATH = "/admin"
CHANGE_PASSWORD_PATH = "/change-password"  # noqa: S105 — a path, not a password
#: ADR-38's panel: a fresh password once per quarter of an hour.
ADMIN_STEP_UP_MINUTES = 15

_WRONG = "That is not right. Try again."


# ── Sign-in ──────────────────────────────────────────────────────────────────


async def stamp_login_flags() -> None:
    """After a sign-in: is this an administrator, and must the password change?"""
    tenant = session_tenant()
    if tenant is None:
        return
    async with AsyncSessionFactory.public() as public:
        admin = await is_instance_admin(
            public,
            subject=tenant.auth_subject,
            email=tenant.email,
            auth_backend=settings.auth_backend,
            admin_emails=settings.instance_admin_emails,
        )
        identity_id = identity_id_of(tenant.auth_subject)
        row = await LocalIdentityService(public).get(identity_id) if identity_id else None
    stamp_admin_flags(
        instance_admin=admin, set_by_admin=row is not None and row.must_change_password
    )


def session_is_admin() -> bool:
    """The navigation's hint; ``/admin`` itself asks the registry."""
    return is_instance_admin_session()


def must_change_password() -> bool:
    return password_set_by_admin()


async def change_own_password(new_password: str) -> None:
    """The signed-in member replaces the password an administrator gave them."""
    tenant = session_tenant()
    identity_id = identity_id_of(tenant.auth_subject) if tenant is not None else None
    if identity_id is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)
    async with AsyncSessionFactory.public() as public:
        identities = LocalIdentityService(public)
        if await identities.verify_password(identity_id, new_password):
            msg = "Choose a password other than the one you were given."
            raise ValidationError(msg)
        await identities.set_password(identity_id, new_password)
    clear_password_set_by_admin()


# ── The panel ────────────────────────────────────────────────────────────────


async def with_admin_service[T](fn: Callable[[InstanceAdminService], Awaitable[T]]) -> T:
    """Run ``fn`` with the signed-in administrator's service; ``NotFoundError`` otherwise."""
    tenant = session_tenant()
    if tenant is None:
        msg = "Not found."
        raise NotFoundError(msg)
    async with AsyncSessionFactory.public() as public:
        service = await InstanceAdminService.for_actor(
            public,
            subject=tenant.auth_subject,
            email=tenant.email,
            auth_backend=settings.auth_backend,
            admin_emails=settings.instance_admin_emails,
            remover=get_auth_provider(),
        )
        return await fn(service)


async def set_login_disabled_as_admin(identity_id: int, disabled: bool) -> None:
    """Disable or enable a login from the panel — and forget what this process holds."""

    async def _set(service: InstanceAdminService) -> None:
        revoked = await service.set_disabled(identity_id, disabled)
        if revoked is not None:
            forget_revoked_member(revoked)

    await with_admin_service(_set)


def admin_step_up_needed() -> bool:
    return not admin_step_up_within(ADMIN_STEP_UP_MINUTES)


async def admin_needs_code() -> bool:
    """Whether the step-up asks for a second-factor code as well as the password."""
    user_id = _user_id()
    async with AsyncSessionFactory() as session:
        if settings.auth_backend == "supabase":
            return await HostedMfaService(session, get_auth_provider()).is_enabled(user_id)
        return await MfaService(session).is_enabled(user_id)


async def prove_admin(password: str, code: str) -> None:
    """Check the administrator's password (and code); stamp the step-up, or raise.

    Counted on the same limiter as the login code prompt: a stolen cookie must
    not buy unlimited guesses at the password.
    """
    tenant = session_tenant()
    if tenant is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)
    user_id = _user_id()
    rate_key = f"admin:{user_id}"
    if mfa_rate_limiter.is_locked(rate_key):
        secs = mfa_rate_limiter.remaining_lock_seconds(rate_key)
        msg = f"Too many attempts. Try again in {secs} seconds."
        raise ValidationError(msg)
    needs_code = await admin_needs_code()
    if not password or (needs_code and not code.strip()):
        msg = "Enter your password" + (" and a code." if needs_code else ".")
        raise ValidationError(msg)
    proved = await verify_admin_credentials(
        tenant.auth_subject, tenant.email, user_id, password, code, needs_code=needs_code
    )
    if not proved:
        mfa_rate_limiter.record_failure(rate_key)
        raise ValidationError(_WRONG)
    mfa_rate_limiter.clear(rate_key)
    mark_admin_step_up()


async def verify_admin_credentials(
    subject: str, email: str, user_id: int, password: str, code: str, *, needs_code: bool
) -> bool:
    """Whether ``password`` (and ``code``) prove this signed-in identity — no stamp, no count.

    ``user_id`` is the identity's row in its family; the family's context must
    be the current one (the page guard sets it).
    """
    if settings.auth_backend == "supabase":
        provider = get_auth_provider()
        if needs_code:
            async with AsyncSessionFactory() as session:
                return await HostedMfaService(session, provider).prove(
                    user_id, email=email, password=password, code=code.strip()
                )
        try:
            identity = await provider.sign_in(email, password)
        except (UnauthorizedError, ValidationError):
            return False
        if isinstance(identity, Identity):
            await provider.sign_out(identity)
            return True
        return False
    identity_id = identity_id_of(subject)
    if identity_id is None:
        return False
    async with AsyncSessionFactory.public() as public:
        if not await LocalIdentityService(public).verify_password(identity_id, password):
            return False
    if not needs_code:
        return True
    async with AsyncSessionFactory() as session:
        return await MfaService(session).verify_challenge(user_id, code.strip())


def _user_id() -> int:
    raw = app.storage.user.get(SESSION_USER_ID)
    if raw is None:
        msg = "Sign in first."
        raise UnauthorizedError(msg)
    return int(raw)
