# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bring a multi-tenant database to head: the registry, then every tenant schema.

What a ``KALETA_TENANCY=multi`` instance does on startup, runnable on its own
as a one-off job before a rollout (ADR-35):

    KALETA_DB_URL=postgresql+asyncpg://… uv run python scripts/migrate_tenants.py
    uv run python scripts/migrate_tenants.py --check   # report only, exit 1 if behind

Exit status: 0 when everything is at head, 1 when ``--check`` finds a schema
behind, 2 when the registry fails to migrate, 3 when a tenant schema failed —
that account is now ``suspended`` and every other one was migrated.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kaleta.config import settings
from kaleta.exceptions import MigrationError
from kaleta.services.setup_service import (
    current_revision,
    ensure_multi_tenant_current,
    head_revision,
    tenant_schema_names,
    tenants_pending_migration,
)


class MigrateTenantsCli:
    def __init__(self, db_url: str, *, check_only: bool) -> None:
        self._db_url = db_url
        self._check_only = check_only

    def run(self) -> int:
        if self._check_only:
            return self._check()
        try:
            run = ensure_multi_tenant_current(self._db_url)
        except MigrationError as exc:
            print(f"migrate_tenants: {exc.message}", file=sys.stderr)
            return 2
        total = len(tenant_schema_names(self._db_url))
        print(f"migrate_tenants: {len(run.migrated)} of {total} tenant schema(s) upgraded to head.")
        for schema in run.suspended:
            print(f"migrate_tenants: {schema} failed to migrate; suspended.", file=sys.stderr)
        return 3 if run.suspended else 0

    def _check(self) -> int:
        registry_behind = current_revision(self._db_url, public=True) != head_revision(public=True)
        pending = tenants_pending_migration(self._db_url)
        if registry_behind:
            print("migrate_tenants: the tenant registry is behind head.")
        for schema in pending:
            print(f"migrate_tenants: {schema} is behind head.")
        if registry_behind or pending:
            return 1
        print("migrate_tenants: everything is at head.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; do not migrate")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if settings.tenancy != "multi":
        print("migrate_tenants: KALETA_TENANCY is not 'multi'; nothing to do.", file=sys.stderr)
        return 2
    return MigrateTenantsCli(settings.db_url, check_only=args.check).run()


if __name__ == "__main__":
    raise SystemExit(main())
