# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fill the configured database with Kaleta's example data.

Run:
    uv run python scripts/seed.py            # add what is missing
    uv run python scripts/seed.py --replace  # rewrite the example data
    uv run python scripts/seed.py --fresh    # drop and recreate the tables first
    uv run python scripts/seed.py --only transactions budgets

A thin wrapper on purpose: the data itself lives in :mod:`kaleta.seeders`, the
same registry the Settings → Data buttons call, so the CLI and the UI cannot
produce two different datasets. Every run is idempotent — a feature that
already has example data is reported as skipped rather than doubled.

With ``KALETA_ENCRYPTION=passphrase`` the data is written under the key a local
key holder's passphrase opens (``KALETA_DATA_PASSPHRASE``, or a prompt);
``--fresh`` keeps that key holder, so the database still opens afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_passphrase import data_passphrase

from kaleta.config import settings
from kaleta.crypto import DataKey
from kaleta.db.base import Base, engine
from kaleta.db.session import AsyncSessionFactory
from kaleta.db.types import use_data_key
from kaleta.seeders import SEED_FEATURE_KEYS, SeedOutcome, seed_features
from kaleta.services.key_service import open_local_data_key

#: Never dropped by ``--fresh``: it holds the only copy of the sealed data key.
_KEPT_TABLES = frozenset({"local_key_material"})


async def _recreate_schema() -> None:
    dropped = [t for t in Base.metadata.sorted_tables if t.name not in _KEPT_TABLES]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.drop_all(sync, tables=dropped))
        await conn.run_sync(Base.metadata.create_all)


async def _data_key() -> DataKey | None:
    if not settings.encryption_enabled:
        return None
    async with AsyncSessionFactory() as session:
        return await open_local_data_key(session, data_passphrase())


async def _ensure_schema() -> None:
    """Create any missing table, so an empty database needs no separate step."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run(*, keys: list[str], replace: bool, fresh: bool) -> list[SeedOutcome]:
    await _ensure_schema()
    data_key = await _data_key()
    if fresh:
        await _recreate_schema()
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
        help="Drop and recreate every table from the models before seeding.",
    )
    args = parser.parse_args()
    keys = list(args.only) if args.only else list(SEED_FEATURE_KEYS)
    outcomes = asyncio.run(run(keys=keys, replace=args.replace, fresh=args.fresh))
    _report(outcomes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
