# SPDX-License-Identifier: AGPL-3.0-or-later
"""``kaleta-admin``: operate the families and logins of a Kaleta instance.

    kaleta-admin list             # families, member count
    kaleta-admin members 12       # who belongs to family 12
    kaleta-admin suspend 12       # refuse its sign-ins
    kaleta-admin resume 12        # let them in again
    kaleta-admin delete 12 --yes  # schema, rows, identities

With ``KALETA_AUTH_BACKEND=local`` (ADR-38) the logins are the registry's too::

    kaleta-admin logins                     # every local login
    kaleta-admin create-login a@b.pl [--admin]
    kaleta-admin reset-password a@b.pl      # prints a new password once
    kaleta-admin reset-password a@b.pl --disable-mfa  # …and drops 2FA
    kaleta-admin registration [closed|invite|open]

Shipped in the package (``scripts/tenant_admin.py`` runs the same from a
checkout), so a container has it: ``podman exec kaleta kaleta-admin …``.

Reads only the ``public`` registry: e-mail addresses, roles, statuses — never a
tenant's data, which is encrypted anyway. Every command that changes something
goes through ``InstanceAdminService``, as the ``/admin`` page does, and writes
the same ``public.admin_audit`` row (with no actor: the operator is whoever
has a shell). A password ``create-login`` or ``reset-password`` prints must be
changed at the next sign-in. (``--disable-mfa`` deletes the
member's second-factor row in their family's schema, and writes the audit row
there, as the UI would.) ``delete`` removes every member's
Supabase identity with ``KALETA_SUPABASE_SERVICE_ROLE_KEY``, drops the schema
and writes one audit line (JSON) to stdout. ``resume`` is how an account
suspended by a failed migration at startup comes back, once fixed.

Exit status: 0 done, 1 refused (unknown family, ``delete`` without ``--yes``,
a provider that could not remove an identity), 2 a local-login command on an
instance whose logins are another provider's.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TextIO

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import KaletaError
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus
from kaleta.schemas.identity import RegistrationMode
from kaleta.services.account_deletion_service import AccountDeletionService, IdentityRemover
from kaleta.services.instance_admin_service import AuthBackend, InstanceAdminService
from kaleta.services.tenant_service import TenantService


class TenantAdminCli:
    """The four (five) commands, over a factory of *public* sessions."""

    def __init__(
        self,
        public_session: Callable[[], AsyncSession],
        remover: IdentityRemover,
        *,
        tenant_session: Callable[[], AsyncSession] | None = None,
        auth_backend: AuthBackend = "local",
        out: TextIO = sys.stdout,
        err: TextIO = sys.stderr,
    ) -> None:
        self._public = public_session
        self._tenant_session = tenant_session
        self._remover = remover
        self._backend: AuthBackend = auth_backend
        self._out = out
        self._err = err

    async def list(self) -> int:
        async with self._public() as session:
            counts = (
                select(TenantMember.tenant_id, func.count(TenantMember.id).label("n"))
                .where(TenantMember.status != TenantMemberStatus.REMOVED)
                .group_by(TenantMember.tenant_id)
                .subquery()
            )
            rows = await session.execute(
                select(Tenant, func.coalesce(counts.c.n, 0))
                .outerjoin(counts, counts.c.tenant_id == Tenant.id)
                .order_by(Tenant.id)
            )
            self._print(f"{'ID':>5}  {'SCHEMA':<16}  {'STATUS':<12}  {'MEMBERS':>7}  LAST SEEN")
            for tenant, members in rows.all():
                seen = tenant.last_seen_at
                seen_text = seen.isoformat(timespec="minutes") if seen is not None else "-"
                self._print(
                    f"{tenant.id:>5}  {tenant.schema_name:<16}  {tenant.status.value:<12}  "
                    f"{members:>7}  {seen_text}"
                )
        return 0

    async def members(self, tenant_id: int) -> int:
        async with self._public() as session:
            if await TenantService(session).get_tenant(tenant_id) is None:
                return self._refuse(f"no tenant {tenant_id}")
            members = await AccountDeletionService(session, self._remover).members(tenant_id)
        for member in members:
            self._print(f"{member.email}\t{member.role.value}\t{member.status.value}")
        return 0

    async def suspend(self, tenant_id: int) -> int:
        async with self._public() as session:
            try:
                tenant = await self._service(session).suspend(tenant_id)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(f"tenant {tenant.id} suspended")
        return 0

    async def resume(self, tenant_id: int) -> int:
        async with self._public() as session:
            try:
                tenant = await self._service(session).resume(tenant_id)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(f"tenant {tenant.id} active")
        return 0

    async def delete(self, tenant_id: int, *, confirmed: bool) -> int:
        if not confirmed:
            return self._refuse(
                "delete drops the account's data and its members' identities for good; "
                "pass --yes to confirm"
            )
        async with self._public() as session:
            try:
                deleted = await self._service(session).delete(tenant_id, typed=None)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(
            json.dumps(
                {
                    "event": "tenant_deleted",
                    "at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "tenant_id": deleted.tenant_id,
                    "schema": deleted.schema,
                    "identities_removed": deleted.identities_removed,
                    "by": "tenant_admin",
                }
            )
        )
        return 0

    # ── Local logins (KALETA_AUTH_BACKEND=local) ──────────────────────────────

    async def logins(self) -> int:
        async with self._public() as session:
            rows = await self._service(session).logins()
        for row in rows:
            marks = (
                ("admin", row.is_admin),
                ("disabled", row.disabled),
                ("must-change", row.must_change_password),
            )
            flags = [name for name, on in marks if on]
            seen = row.last_login_at.isoformat(timespec="seconds") if row.last_login_at else "-"
            self._print(f"{row.identity_id}\t{row.email}\t{','.join(flags) or '-'}\t{seen}")
        return 0

    async def create_login(self, email: str, *, admin: bool) -> int:
        async with self._public() as session:
            try:
                login = await self._service(session).create_login(email, admin=admin)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(
            f"login {login.identity_id} {login.email} created; "
            f"password (shown once): {login.password}"
        )
        return 0

    async def reset_password(self, email: str, *, disable_mfa: bool = False) -> int:
        async with self._public() as session:
            service = self._service(session)
            try:
                login = await service.login_by_email(email)
                reset = await service.reset_password(login.identity_id, disable_mfa=disable_mfa)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(
            f"login {reset.login.identity_id} {reset.login.email}: "
            f"new password (shown once): {reset.login.password}"
        )
        if reset.sessions_revoked:
            self._print(
                "All browser sessions have been signed out; API bearer tokens are unchanged."
            )
        if reset.mfa_removed is not None:
            if not reset.in_family:
                self._print("two-factor authentication: none (no family yet)")
            else:
                self._print(
                    f"two-factor authentication: {'removed' if reset.mfa_removed else 'none'}"
                )
        return 0

    async def registration(self, mode: RegistrationMode | None) -> int:
        async with self._public() as session:
            service = self._service(session)
            if mode is not None:
                await service.set_registration_mode(mode)
            current = await service.registration_mode()
        self._print(f"registration {current.value}")
        return 0

    def _service(self, session: AsyncSession) -> InstanceAdminService:
        return InstanceAdminService.for_operator(
            session,
            auth_backend=self._backend,
            remover=self._remover,
            tenant_session=self._tenant_session,
        )

    def _print(self, line: str) -> None:
        self._out.write(f"{line}\n")

    def _refuse(self, message: str) -> int:
        self._err.write(f"kaleta-admin: {message}\n")
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kaleta-admin", description=(__doc__ or "").splitlines()[0]
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="every tenant with its member count")
    for name, text in (
        ("members", "the members of one tenant"),
        ("suspend", "refuse every sign-in to one tenant"),
        ("resume", "make a suspended tenant active again"),
        ("delete", "drop one tenant's schema and delete its members' identities"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("tenant_id", type=int)
        if name == "delete":
            command.add_argument("--yes", action="store_true", help="confirm the deletion")
    commands.add_parser("logins", help="every local login (KALETA_AUTH_BACKEND=local)")
    create = commands.add_parser("create-login", help="a new local login; prints its password")
    create.add_argument("email")
    create.add_argument("--admin", action="store_true", help="make it an instance administrator")
    reset = commands.add_parser("reset-password", help="a new password for a local login")
    reset.add_argument("email")
    reset.add_argument(
        "--disable-mfa", action="store_true", help="also turn the login's two-factor sign-in off"
    )
    registration = commands.add_parser("registration", help="show or set who may sign up")
    registration.add_argument("mode", nargs="?", choices=[m.value for m in RegistrationMode])
    return parser


_LOCAL_COMMANDS = frozenset({"logins", "create-login", "reset-password", "registration"})


async def _run(args: argparse.Namespace) -> int:
    from kaleta.auth.providers import get_auth_provider
    from kaleta.config import settings
    from kaleta.db import AsyncSessionFactory

    # Never echo SQL here, even with KALETA_DEBUG: stdout carries the audit line.
    AsyncSessionFactory.configure(settings.db_url)
    cli = TenantAdminCli(
        AsyncSessionFactory.public,
        get_auth_provider(),
        tenant_session=AsyncSessionFactory,
        auth_backend=settings.auth_backend,
    )
    try:
        if args.command == "list":
            return await cli.list()
        if args.command == "members":
            return await cli.members(args.tenant_id)
        if args.command == "suspend":
            return await cli.suspend(args.tenant_id)
        if args.command == "resume":
            return await cli.resume(args.tenant_id)
        if args.command in _LOCAL_COMMANDS and settings.auth_backend != "local":
            sys.stderr.write(f"kaleta-admin: {args.command} needs KALETA_AUTH_BACKEND=local.\n")
            return 2
        if args.command == "logins":
            return await cli.logins()
        if args.command == "create-login":
            return await cli.create_login(args.email, admin=args.admin)
        if args.command == "reset-password":
            return await cli.reset_password(args.email, disable_mfa=args.disable_mfa)
        if args.command == "registration":
            mode = RegistrationMode(args.mode) if args.mode else None
            return await cli.registration(mode)
        return await cli.delete(args.tenant_id, confirmed=args.yes)
    finally:
        await AsyncSessionFactory.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return asyncio.run(_run(args))


def entry_point() -> None:
    """``[project.scripts] kaleta-admin``."""
    raise SystemExit(main())
