# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fill a family's schema with Kaleta's example data.

Run:
    uv run python scripts/seed.py            # add what is missing
    uv run python scripts/seed.py --replace  # rewrite the example data
    uv run python scripts/seed.py --fresh    # drop and recreate the family's tables first
    uv run python scripts/seed.py --only transactions budgets
    uv run python scripts/seed.py --family 3 # on an instance with more than one family

A thin wrapper on purpose: the data itself lives in :mod:`kaleta.seeders`, the
same registry the Settings → Data buttons call, so the CLI and the UI cannot
produce two different datasets. Every run is idempotent — a feature that
already has example data is reported as skipped rather than doubled.

Without ``--family`` the instance's only family is used. With encryption on
(every production instance) the data is written under the key a member's
passphrase opens (``KALETA_DATA_PASSPHRASE``, or a prompt); the key block is
the registry's, so ``--fresh`` leaves it where it is and the family still
opens afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_passphrase import data_passphrase
from sqlalchemy.ext.asyncio import create_async_engine

from kaleta.config import settings
from kaleta.crypto import DataKey
from kaleta.db.base import Base
from kaleta.db.session import AsyncSessionFactory
from kaleta.db.tenant_context import TenantContext, use_tenant
from kaleta.db.types import use_data_key
from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.tenant import TenantStatus
from kaleta.seeders import SEED_FEATURE_KEYS, SeedOutcome, seed_features
from kaleta.services.key_service import open_family_data_key
from kaleta.services.tenant_service import TenantService


async def _family(family_id: int | None) -> TenantContext:
    async with AsyncSessionFactory.public() as public:
        tenants = [
            t for t in await TenantService(public).list_tenants() if t.status is TenantStatus.ACTIVE
        ]
    if family_id is not None:
        tenants = [t for t in tenants if t.id == family_id]
        if not tenants:
            msg = f"No active family {family_id}."
            raise NotFoundError(msg)
    if not tenants:
        msg = "No family yet: sign in once, which sets the first one up."
        raise NotFoundError(msg)
    if len(tenants) > 1:
        ids = ", ".join(str(t.id) for t in tenants)
        msg = f"More than one family ({ids}): choose one with --family."
        raise ValidationError(msg)
    return TenantContext(tenant_id=tenants[0].id, schema=tenants[0].schema_name)


async def _recreate_schema(family: TenantContext) -> None:
    engine = create_async_engine(settings.db_url)
    try:
        async with engine.begin() as conn:
            translated = await conn.execution_options(schema_translate_map={None: family.schema})
            await translated.run_sync(Base.metadata.drop_all)
            await translated.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _data_key(family: TenantContext) -> DataKey | None:
    if not settings.encryption_enabled:
        return None
    async with AsyncSessionFactory.public() as public, AsyncSessionFactory() as data:
        return await open_family_data_key(public, data, family.tenant_id, data_passphrase())


async def run(
    *, keys: list[str], replace: bool, fresh: bool, family_id: int | None = None
) -> list[SeedOutcome]:
    family = await _family(family_id)
    with use_tenant(family):
        data_key = await _data_key(family)
        if fresh:
            await _recreate_schema(family)
        with use_data_key(data_key):
            async with AsyncSessionFactory() as session:
                return await seed_features(session, keys, replace=replace)


def _report(outcomes: list[SeedOutcome]) -> None:
    seeded = [outcome for outcome in outcomes if not outcome.skipped]
    skipped = [outcome.key for outcome in outcomes if outcome.skipped]
    for outcome in seeded:
        detail = ", ".join(f"{count} {table}" for table, count in sorted(outcome.counts.items()))
        print(f"[OK] {outcome.key}: {detail}")
    if skipped:
        print(f"[--] already had example data, left alone: {', '.join(skipped)}")
    print(f"[OK] {sum(outcome.total for outcome in seeded)} rows written in total.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="FEATURE",
        choices=SEED_FEATURE_KEYS,
        help=f"Seed only these features (and what they need): {', '.join(SEED_FEATURE_KEYS)}",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Rewrite the chosen features' example data instead of skipping what is there.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Drop and recreate the family's tables from the models before seeding.",
    )
    parser.add_argument(
        "--family", type=int, help="The family to seed (required with more than one)."
    )
    args = parser.parse_args()
    keys = list(args.only) if args.only else list(SEED_FEATURE_KEYS)
    try:
        outcomes = asyncio.run(
            run(keys=keys, replace=args.replace, fresh=args.fresh, family_id=args.family)
        )
    except (NotFoundError, ValidationError) as exc:
        print(f"seed: {exc.message}", file=sys.stderr)
        return 1
    _report(outcomes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
