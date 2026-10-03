#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operate the accounts of a hosted (``KALETA_TENANCY=multi``) Kaleta.

    uv run python scripts/tenant_admin.py list             # tenants, member count
    uv run python scripts/tenant_admin.py members 12       # who belongs to tenant 12
    uv run python scripts/tenant_admin.py suspend 12       # refuse its sign-ins
    uv run python scripts/tenant_admin.py resume 12        # let them in again
    uv run python scripts/tenant_admin.py delete 12 --yes  # schema, rows, identities

Reads only the ``public`` registry: e-mail addresses, roles, statuses — never a
tenant's data, which is encrypted anyway. ``delete`` removes every member's
Supabase identity with ``KALETA_SUPABASE_SERVICE_ROLE_KEY``, drops the schema
and writes one audit line (JSON) to stdout. ``resume`` is how an account
suspended by a failed migration at startup comes back, once fixed.

Exit status: 0 done, 1 refused (unknown tenant, ``delete`` without ``--yes``,
a provider that could not remove an identity), 2 not a multi-tenant instance.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import KaletaError
from kaleta.models.tenant import Tenant, TenantMember, TenantMemberStatus
from kaleta.services.account_deletion_service import AccountDeletionService, IdentityRemover
from kaleta.services.tenant_service import TenantService


class TenantAdminCli:
    """The four (five) commands, over a factory of *public* sessions."""

    def __init__(
        self,
        public_session: Callable[[], AsyncSession],
        remover: IdentityRemover,
        *,
        out: TextIO = sys.stdout,
        err: TextIO = sys.stderr,
    ) -> None:
        self._public = public_session
        self._remover = remover
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
                tenant = await TenantService(session).suspend(tenant_id)
            except KaletaError as exc:
                return self._refuse(exc.message)
        self._print(f"tenant {tenant.id} suspended")
        return 0

    async def resume(self, tenant_id: int) -> int:
        async with self._public() as session:
            try:
                tenant = await TenantService(session).resume(tenant_id)
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
                deleted = await AccountDeletionService(session, self._remover).delete(tenant_id)
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

    def _print(self, line: str) -> None:
        print(line, file=self._out)

    def _refuse(self, message: str) -> int:
        print(f"tenant_admin: {message}", file=self._err)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
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
    return parser


async def _run(args: argparse.Namespace) -> int:
    from kaleta.auth.providers import get_auth_provider
    from kaleta.config import settings
    from kaleta.db import AsyncSessionFactory

    # Never echo SQL here, even with KALETA_DEBUG: stdout carries the audit line.
    AsyncSessionFactory.configure(settings.db_url)
    cli = TenantAdminCli(AsyncSessionFactory.public, get_auth_provider())
    try:
        if args.command == "list":
            return await cli.list()
        if args.command == "members":
            return await cli.members(args.tenant_id)
        if args.command == "suspend":
            return await cli.suspend(args.tenant_id)
        if args.command == "resume":
            return await cli.resume(args.tenant_id)
        return await cli.delete(args.tenant_id, confirmed=args.yes)
    finally:
        await AsyncSessionFactory.dispose()


def main() -> int:
    args = _parser().parse_args()
    from kaleta.config import settings

    if settings.tenancy != "multi":
        print("tenant_admin: KALETA_TENANCY is not 'multi'; nothing to do.", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
