# SPDX-License-Identifier: AGPL-3.0-or-later
"""DataService — clear all data and/or fill it with realistic example data.

Two kinds of seeding live here, and they are not the same thing:

``seed``
    The demo reset. It **wipes the seedable tables first** and then fills every
    feature in, so the result is one coherent story and not a mix of what was
    already there. ``scripts/reset_demo.py`` and the Settings "Populate with
    example data" button use it, and a caller must mean it.

``seed_features`` / ``seed_everything`` / ``seed_status``
    The per-feature seeders in :mod:`kaleta.seeders`, which add what is missing
    and touch nothing else. This is what the Example data buttons use, and it
    is safe to press twice.

Both go through the same registry, which is the point: the CLI, the demo reset
and the buttons cannot show three different datasets.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account
from kaleta.models.asset import Asset
from kaleta.models.audit_log import AuditLog
from kaleta.models.budget import Budget
from kaleta.models.categorisation_rule import CategorisationRule
from kaleta.models.category import Category
from kaleta.models.credit import CreditCardProfile, LoanProfile
from kaleta.models.currency_rate import CurrencyRate
from kaleta.models.dismissed_candidate import DismissedCandidate
from kaleta.models.institution import Institution
from kaleta.models.payee import Payee
from kaleta.models.personal_loan import Counterparty, PersonalLoan, PersonalLoanRepayment
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.report import SavedReport
from kaleta.models.reserve_fund import ReserveFund
from kaleta.models.subscription import Subscription
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionSplit
from kaleta.seeders import SeedOutcome, seed_all, seed_features, seed_status

#: Every table the example data can occupy, dependants before what they hang
#: off. Users, API tokens and bug reports are deliberately absent: wiping the
#: ledger must not take the login with it.
_CLEARED_MODELS = (
    TransactionSplit,
    Transaction,
    Budget,
    PlannedTransaction,
    Subscription,
    DismissedCandidate,
    ReserveFund,
    PersonalLoanRepayment,
    PersonalLoan,
    Counterparty,
    CreditCardProfile,
    LoanProfile,
    CategorisationRule,
    CurrencyRate,
    AuditLog,
    Asset,
    SavedReport,
    Tag,
    Account,
    Category,
    Institution,
    Payee,
)


async def _set_sqlite_foreign_keys(session: AsyncSession, *, enabled: bool) -> None:
    """Toggle SQLite FK enforcement. No-op on PostgreSQL."""
    conn = await session.connection()
    if conn.dialect.name != "sqlite":
        return
    await session.execute(text(f"PRAGMA foreign_keys = {'ON' if enabled else 'OFF'}"))


class DataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def clear_all(self) -> None:
        """Delete every row the example data can occupy, preserving the schema."""
        s = self.session
        await _set_sqlite_foreign_keys(s, enabled=False)
        try:
            for model in _CLEARED_MODELS:
                await s.execute(delete(model))
            # The many-to-many join table has no ORM class of its own.
            await s.execute(text("DELETE FROM transaction_tags"))
            await s.commit()
        finally:
            await _set_sqlite_foreign_keys(s, enabled=True)

    async def seed_features(
        self,
        keys: list[str],
        *,
        replace: bool = False,
    ) -> list[SeedOutcome]:
        """Fill in the named features (and what they stand on) without wiping."""
        return await seed_features(self.session, keys, replace=replace)

    async def seed_everything(self, *, replace: bool = False) -> list[SeedOutcome]:
        """Fill in every feature that has no example data yet."""
        return await seed_all(self.session, replace=replace)

    async def seed_status(self) -> dict[str, int]:
        """Rows already owned per feature, so a button can say what it would skip."""
        return await seed_status(self.session)

    async def seed(self) -> dict[str, int]:
        """Wipe, then write the whole example dataset. Returns rows per table."""
        await self.clear_all()
        outcomes = await self.seed_everything()

        # The audit log records the seed's own writes, which is noise nobody
        # asked for — the point of a fresh demo is a clean history.
        await self.session.execute(delete(AuditLog))
        await self.session.commit()

        totals: dict[str, int] = defaultdict(int)
        for outcome in outcomes:
            for table, count in outcome.counts.items():
                totals[table] += count
        return dict(totals)
