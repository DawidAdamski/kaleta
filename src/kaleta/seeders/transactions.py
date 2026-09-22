# SPDX-License-Identifier: AGPL-3.0-or-later
"""Six years of transactions, with their merchants and tags.

The generator the demo data has always used, moved out of ``scripts/seed.py``
so the Settings button and the CLI run the same code. Its shape is what makes
the rest of the app testable on example data: a salary and a rent every month,
seasonal spending, a summer holiday, a December splurge, an occasional invoice
and refund, and an internal transfer to savings whose two legs are linked.

Tags are not decoration — ``KAL-PLT-004`` says every expense declares how it
was paid, both legs of a transfer carry ``Transfer``, subscription spend
carries ``Subscription`` and ``Recurring``, and income carries nothing.
"""

from __future__ import annotations

import datetime
import random
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import Account, AccountType
from kaleta.models.category import Category
from kaleta.models.payee import Payee
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionSplit, TransactionType
from kaleta.seeders.base import Seeder, inflation, month_offset, rng, row_count, salary, zloty
from kaleta.seeders.catalog import (
    BASE_BUDGETS,
    CATCH_PHRASES,
    CATEGORY_PAYEES,
    EXPENSE_CATEGORIES,
    FALLBACK_PAYEE_CHANCE,
    FALLBACK_PAYEES,
    HOLIDAY_DESTINATIONS,
    MONTHS,
    ONLINE_MERCHANTS,
    PAYEE_ASSIGN_CHANCE,
    REFUNDABLE_CATEGORIES,
    REFUNDABLE_CHANCE,
    SEASONAL,
)
from kaleta.seeders.lookups import (
    accounts_by_kind,
    categories_by_name,
    payees_by_name,
    subscription_category_ids,
    tags_by_name,
)


class TransactionsSeeder(Seeder):
    key = "transactions"
    depends_on = ("taxonomy", "accounts")
    icon = "receipt_long"

    async def count(self, session: AsyncSession) -> int:
        return await row_count(session, Transaction)

    async def create(self, session: AsyncSession) -> dict[str, int]:
        generator = rng(salt=1)
        accounts = await accounts_by_kind(session)
        categories = await categories_by_name(session)
        tags = await tags_by_name(session)
        payees = await payees_by_name(session)
        subscription_ids = await subscription_category_ids(session)

        builder = _LedgerBuilder(
            session=session,
            generator=generator,
            accounts=accounts,
            categories=categories,
            tags=tags,
            payees=payees,
            subscription_ids=subscription_ids,
        )
        await builder.run()
        return {"transactions": builder.written, "transfer_pairs": builder.transfer_pairs}

    async def remove(self, session: AsyncSession) -> None:
        await session.execute(text("DELETE FROM transaction_tags"))
        await session.execute(delete(TransactionSplit))
        await session.execute(delete(Transaction))


class _LedgerBuilder:
    """One pass over the months, writing the rows and the balances they imply."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        generator: random.Random,
        accounts: dict[str, Account],
        categories: dict[str, Category],
        tags: dict[str, Tag],
        payees: dict[str, Payee],
        subscription_ids: set[int],
    ) -> None:
        self.session = session
        self.rng = generator
        self.accounts = accounts
        self.categories = categories
        self.tags = tags
        self.payees = payees
        self.subscription_ids = subscription_ids
        self.written = 0
        self.transfer_pairs = 0
        self.balance: dict[int, Decimal] = defaultdict(Decimal)
        self.expense_categories = [categories[name] for name in EXPENSE_CATEGORIES]

    # ── row helpers ───────────────────────────────────────────────────────────

    def _pick_payee(self, category_name: str) -> Payee | None:
        """The merchant for an expense, or None — not every row names one."""
        pool = CATEGORY_PAYEES.get(category_name)
        if pool is not None:
            if self.rng.random() >= PAYEE_ASSIGN_CHANCE:
                return None
            return self.payees[self.rng.choice(pool)]
        if self.rng.random() >= FALLBACK_PAYEE_CHANCE:
            return None
        return self.payees[self.rng.choice(FALLBACK_PAYEES)]

    def _expense_tags(self, account: Account, category: Category, payee: Payee | None) -> list[Tag]:
        """How the expense was paid, plus what kind of spend it is."""
        online = payee is not None and payee.name in ONLINE_MERCHANTS
        chosen = [self.tags["Cash" if account.type == AccountType.CASH else "Card"]]
        if online:
            chosen.append(self.tags["Online"])
        if category.id in self.subscription_ids:
            chosen.append(self.tags["Subscription"])
            chosen.append(self.tags["Recurring"])
        refundable = category.name in REFUNDABLE_CATEGORIES or online
        if refundable and self.rng.random() < REFUNDABLE_CHANCE:
            chosen.append(self.tags["Refundable"])
        return chosen

    def _add(
        self,
        transaction: Transaction,
        *,
        payee: Payee | None = None,
        tags: list[Tag] | None = None,
    ) -> None:
        if payee is not None:
            transaction.payee_id = payee.id
        # Added before the tags are linked: the tags are already persistent, and
        # appending to a row the session does not hold yet drops the
        # association without a word.
        self.session.add(transaction)
        if tags:
            transaction.tags.extend(tags)
        self.written += 1
        if transaction.type == TransactionType.INCOME:
            self.balance[transaction.account_id] += transaction.amount
        elif transaction.type == TransactionType.EXPENSE:
            self.balance[transaction.account_id] -= transaction.amount

    def _add_expense(self, transaction: Transaction, account: Account, category: Category) -> None:
        payee = self._pick_payee(category.name)
        self._add(transaction, payee=payee, tags=self._expense_tags(account, category, payee))

    # ── the pass ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        today = datetime.date.today()
        checking = self.accounts["checking"]
        savings = self.accounts["savings"]
        cash = self.accounts["cash"]
        credit = self.accounts["credit"]

        for months_back in range(MONTHS):
            year, month = month_offset(today, months_back)
            seasonal = SEASONAL[month]
            factor = inflation(months_back)

            self._add(
                Transaction(
                    account_id=checking.id,
                    category_id=self.categories["Wynagrodzenie"].id,
                    amount=salary(months_back, self.rng),
                    type=TransactionType.INCOME,
                    date=datetime.date(year, month, 1),
                    description=f"Wynagrodzenie {month:02d}/{year}",
                )
            )

            rent = self.categories["Mieszkanie & Czynsz"]
            self._add_expense(
                Transaction(
                    account_id=checking.id,
                    category_id=rent.id,
                    amount=zloty(float(BASE_BUDGETS["Mieszkanie & Czynsz"]) * factor),
                    type=TransactionType.EXPENSE,
                    date=datetime.date(year, month, 5),
                    description="Czynsz za mieszkanie",
                ),
                checking,
                rent,
            )

            for _ in range(self.rng.randint(12, 22)):
                category = self.rng.choice(self.expense_categories)
                account = self.rng.choice([checking, cash, credit])
                self._add_expense(
                    Transaction(
                        account_id=account.id,
                        category_id=category.id,
                        amount=zloty(self.rng.uniform(8, 600) * seasonal * factor),
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, self.rng.randint(1, 28)),
                        description=self.rng.choice(CATCH_PHRASES),
                    ),
                    account,
                    category,
                )

            if month in (7, 8) and self.rng.random() < 0.6:
                holiday = self.categories["Wakacje & Podróże"]
                self._add_expense(
                    Transaction(
                        account_id=checking.id,
                        category_id=holiday.id,
                        amount=zloty(self.rng.uniform(1500, 5000) * factor),
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, self.rng.randint(1, 20)),
                        description=f"{self.rng.choice(HOLIDAY_DESTINATIONS)} — wakacje",
                    ),
                    checking,
                    holiday,
                )

            if month == 12 and self.rng.random() < 0.5:
                electronics = self.categories["Elektronika"]
                self._add_expense(
                    Transaction(
                        account_id=credit.id,
                        category_id=electronics.id,
                        amount=zloty(self.rng.uniform(800, 3500) * factor),
                        type=TransactionType.EXPENSE,
                        date=datetime.date(year, month, self.rng.randint(10, 23)),
                        description="Prezenty świąteczne / elektronika",
                    ),
                    credit,
                    electronics,
                )

            if self.rng.random() < 0.35:
                self._add(
                    Transaction(
                        account_id=checking.id,
                        category_id=self.categories["Freelance"].id,
                        amount=zloty(self.rng.uniform(400, 4000) * factor),
                        type=TransactionType.INCOME,
                        date=datetime.date(year, month, self.rng.randint(10, 25)),
                        description="Faktura freelance",
                    )
                )

            if self.rng.random() < 0.15:
                self._add(
                    Transaction(
                        account_id=checking.id,
                        category_id=self.categories["Zwroty"].id,
                        amount=zloty(self.rng.uniform(20, 300) * factor),
                        type=TransactionType.INCOME,
                        date=datetime.date(year, month, self.rng.randint(1, 28)),
                        description="Zwrot / reklamacja",
                    )
                )

            await self._add_transfer(checking, savings, year, month, factor)

        for account in self.accounts.values():
            account.balance = self.balance[account.id]

    async def _add_transfer(
        self,
        source: Account,
        target: Account,
        year: int,
        month: int,
        factor: float,
    ) -> None:
        """One month's own-money move, as the two linked legs it really is."""
        amount = zloty(self.rng.uniform(300, 1500) * factor)
        on = datetime.date(year, month, 15)
        out_leg = Transaction(
            account_id=source.id,
            category_id=None,
            amount=amount,
            type=TransactionType.TRANSFER,
            date=on,
            description=f"Przelew własny → oszczędności {month:02d}/{year}",
            is_internal_transfer=True,
        )
        in_leg = Transaction(
            account_id=target.id,
            category_id=None,
            amount=amount,
            type=TransactionType.TRANSFER,
            date=on,
            description=f"Przelew własny ← konto główne {month:02d}/{year}",
            is_internal_transfer=True,
        )
        self.session.add_all([out_leg, in_leg])
        out_leg.tags.append(self.tags["Transfer"])
        in_leg.tags.append(self.tags["Transfer"])
        await self.session.flush()
        out_leg.linked_transaction_id = in_leg.id
        in_leg.linked_transaction_id = out_leg.id
        self.balance[source.id] -= amount
        self.balance[target.id] += amount
        self.written += 2
        self.transfer_pairs += 1
