# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration coverage for the per-feature example data.

Covers: KAL-PLT-006, KAL-PLT-007, KAL-PLT-008, KAL-PLT-009, KAL-SET-029
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import kaleta.models  # noqa: F401 — register ORM tables on Base.metadata
from kaleta.config import settings
from kaleta.debug_info import MASK, build_sections, sections_as_markdown
from kaleta.models.account import Account
from kaleta.models.asset import Asset
from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.credit import CreditCardProfile
from kaleta.models.institution import Institution
from kaleta.models.payee import Payee
from kaleta.models.personal_loan import Counterparty, PersonalLoan, PersonalLoanRepayment
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.reserve_fund import ReserveFund
from kaleta.models.subscription import Subscription
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction
from kaleta.seeders import SEED_FEATURE_KEYS, seed_all, seed_features
from tests.script_family import ScriptFamily, script_family

# Slow tier (test-suite-speed): seed CLIs in subprocesses, whole-dataset seeding.
pytestmark = pytest.mark.slow

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed.py"

#: Every table the example data occupies. Compared table by table, so a seeder
#: that quietly stops writing one of them fails rather than averages out.
SEEDED_TABLES = (
    Account,
    Asset,
    Budget,
    Category,
    Counterparty,
    CreditCardProfile,
    Institution,
    Payee,
    PersonalLoan,
    PersonalLoanRepayment,
    PlannedTransaction,
    ReserveFund,
    Subscription,
    Tag,
    Transaction,
)


async def _counts(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for model in SEEDED_TABLES:
        result = await session.execute(select(func.count()).select_from(model))
        counts[model.__tablename__] = int(result.scalar_one())
    return counts


def _family_counts(family: ScriptFamily) -> dict[str, int]:
    async def _read() -> dict[str, int]:
        async with family.session() as session:
            return await _counts(session)

    return asyncio.run(_read())


def _run_seed_cli(
    tmp_path: Path, family: ScriptFamily, *args: str
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, str(SEED_SCRIPT), *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "HOME": str(home), **family.env},
        check=False,
        capture_output=True,
        text=True,
    )


async def test_seed_everything_fills_every_feature_once(session: AsyncSession) -> None:
    """Covers: KAL-PLT-006"""
    outcomes = await seed_all(session)
    assert [outcome.key for outcome in outcomes] == list(SEED_FEATURE_KEYS)
    first = await _counts(session)
    assert all(count > 0 for count in first.values()), first

    again = await seed_all(session)
    assert all(outcome.skipped for outcome in again)
    assert await _counts(session) == first


async def test_seeding_accounts_leaves_the_other_tables_empty(session: AsyncSession) -> None:
    """Covers: KAL-PLT-007"""
    await seed_features(session, ["accounts"])
    counts = await _counts(session)
    assert counts["accounts"] > 0
    assert counts["institutions"] > 0
    for table in ("transactions", "budgets", "categories", "planned_transactions"):
        assert counts[table] == 0, table


def test_cli_and_registry_produce_the_same_dataset(tmp_path: Path) -> None:
    """Covers: KAL-PLT-008

    Two families provisioned alike, so both start from the subscriptions tree
    a family schema is migrated with.
    """
    cli = script_family("example_cli")
    proc = _run_seed_cli(tmp_path, cli)
    assert proc.returncode == 0, proc.stderr or proc.stdout

    registry = script_family("example_registry")

    async def _seed() -> None:
        async with registry.session() as session:
            await seed_all(session)

    asyncio.run(_seed())
    assert _family_counts(cli) == _family_counts(registry)


def test_the_cli_is_idempotent_too(tmp_path: Path) -> None:
    """Covers: KAL-PLT-006"""
    family = script_family("example_twice")
    first = _run_seed_cli(tmp_path, family)
    assert first.returncode == 0, first.stderr or first.stdout

    before = _family_counts(family)
    second = _run_seed_cli(tmp_path, family)
    assert second.returncode == 0, second.stderr or second.stdout
    assert "left alone" in second.stdout
    assert _family_counts(family) == before


async def test_replace_rewrites_the_dataset_with_foreign_keys_enforced(
    session: AsyncSession,
) -> None:
    """Covers: KAL-PLT-009"""
    await seed_all(session)
    before = await _counts(session)

    # Deleting the categories and accounts a live ledger points at is an
    # integrity error, not a fresh start: the whole dataset has to come out in
    # reverse dependency order first.
    await seed_all(session, replace=True)

    assert await _counts(session) == before


async def test_replacing_one_feature_takes_what_stands_on_it(session: AsyncSession) -> None:
    """Covers: KAL-PLT-009"""
    await seed_all(session)
    before = await _counts(session)
    assets_before = {
        asset.id: asset.name for asset in (await session.execute(select(Asset))).scalars().all()
    }

    outcomes = await seed_features(session, ["accounts"], replace=True)

    # The ledger, the plan, the funds and the card all hang off the accounts,
    # so they are rebuilt with them.
    rewritten = {outcome.key for outcome in outcomes if not outcome.skipped}
    assert {"accounts", "transactions", "planned", "reserve_funds"} <= rewritten
    assert await _counts(session) == before

    # Assets stand on nothing and were not asked for — untouched.
    assets_after = {
        asset.id: asset.name for asset in (await session.execute(select(Asset))).scalars().all()
    }
    assert assets_after == assets_before


def test_cli_replace_survives_a_seeded_database(tmp_path: Path) -> None:
    """Covers: KAL-PLT-009

    End to end through ``scripts/seed.py``, in a family of its own. The first
    ``--replace`` also clears the English tags and subscription children the
    family's migrations planted (taxonomy owns those whole tables), so it is
    the second one that must leave every count where it was.
    """
    family = script_family("example_replace")
    first = _run_seed_cli(tmp_path, family)
    assert first.returncode == 0, first.stderr or first.stdout
    again = _run_seed_cli(tmp_path, family, "--replace")
    assert again.returncode == 0, again.stderr or again.stdout

    before = _family_counts(family)
    assert all(count > 0 for count in before.values()), before
    third = _run_seed_cli(tmp_path, family, "--replace")
    assert third.returncode == 0, third.stderr or third.stdout
    assert _family_counts(family) == before


def test_debug_report_is_markdown_without_secrets() -> None:
    """Covers: KAL-SET-029"""
    markdown = sections_as_markdown(build_sections(storage_keys={"language": "str"}))

    assert markdown.startswith("## Kaleta debug info")
    assert markdown.count("\n") > 10
    assert "### Versions" in markdown
    assert f"| secret_key | `{MASK}` |" in markdown

    # The value actually in force must not appear anywhere in the report — not
    # under its own key and not inside a database URL.
    if settings.secret_key:
        assert settings.secret_key not in markdown
