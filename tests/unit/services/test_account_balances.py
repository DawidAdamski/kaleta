# SPDX-License-Identifier: AGPL-3.0-or-later
"""Account balances derived from the ledger (plan accounts-ledger-balances).

Covers: KAL-ACC-005, KAL-ACC-006, KAL-ACC-007, KAL-ACC-008
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ValidationError
from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.planned_transaction import RecurrenceFrequency
from kaleta.models.transaction import Transaction, TransactionType, TransferDirection
from kaleta.schemas.account import AccountCreate, AccountUpdate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.planned_transaction import PlannedTransactionCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionUpdate
from kaleta.services import AccountService, CategoryService, TransactionService
from kaleta.services.planned_transaction_service import PlannedTransactionService

DAY = datetime.date(2026, 9, 15)


class _Books:
    """Two accounts and the two categories a ledger row needs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.accounts = AccountService(session)
        self.txs = TransactionService(session)

    async def setup(self) -> _Books:
        categories = CategoryService(self.session)
        self.food = (
            await categories.create(CategoryCreate(name="Jedzenie", type=CategoryType.EXPENSE))
        ).id
        self.salary = (
            await categories.create(CategoryCreate(name="Pensja", type=CategoryType.INCOME))
        ).id
        return self

    async def account(self, name: str, balance: str) -> int:
        created = await self.accounts.create(
            AccountCreate(name=name, type=AccountType.CHECKING, balance=Decimal(balance))
        )
        return created.id

    async def expense(self, account_id: int, amount: str, day: datetime.date = DAY) -> int:
        tx = await self.txs.create(
            TransactionCreate(
                account_id=account_id,
                category_id=self.food,
                amount=Decimal(amount),
                type=TransactionType.EXPENSE,
                date=day,
            )
        )
        return tx.id

    async def income(self, account_id: int, amount: str) -> int:
        tx = await self.txs.create(
            TransactionCreate(
                account_id=account_id,
                category_id=self.salary,
                amount=Decimal(amount),
                type=TransactionType.INCOME,
                date=DAY,
            )
        )
        return tx.id

    async def transfer(self, source: int, target: int, amount: str) -> tuple[int, int]:
        def leg(account_id: int, direction: TransferDirection) -> TransactionCreate:
            return TransactionCreate(
                account_id=account_id,
                amount=Decimal(amount),
                type=TransactionType.TRANSFER,
                transfer_direction=direction,
                date=DAY,
                is_internal_transfer=True,
            )

        out, incoming = await self.txs.create_transfer(
            leg(source, TransferDirection.OUT), leg(target, TransferDirection.IN)
        )
        return out.id, incoming.id

    async def balance(self, account_id: int) -> Decimal:
        return await self.accounts.balance(account_id)


@pytest.fixture
async def books(session: AsyncSession) -> _Books:
    return await _Books(session).setup()


class TestScenarios:
    async def test_balance_follows_income_and_expenses(self, books: _Books) -> None:
        """Covers: KAL-ACC-005"""
        pko = await books.account("PKO Main", "1000.00")
        await books.expense(pko, "200.00")
        await books.income(pko, "50.00")
        assert await books.balance(pko) == Decimal("850.00")

    async def test_a_transfer_moves_both_balances(self, books: _Books) -> None:
        """Covers: KAL-ACC-006"""
        pko = await books.account("PKO Main", "1000.00")
        savings = await books.account("Oszczędności", "0.00")
        await books.transfer(pko, savings, "500.00")
        assert await books.balance(pko) == Decimal("500.00")
        assert await books.balance(savings) == Decimal("500.00")

    async def test_editing_or_deleting_moves_the_balance_back(self, books: _Books) -> None:
        """Covers: KAL-ACC-007"""
        pko = await books.account("PKO Main", "1000.00")
        expense = await books.expense(pko, "200.00")
        await books.txs.update(expense, TransactionUpdate(amount=Decimal("150.00")))
        assert await books.balance(pko) == Decimal("850.00")
        await books.txs.delete(expense)
        assert await books.balance(pko) == Decimal("1000.00")

    async def test_setting_the_current_balance_by_hand(self, books: _Books) -> None:
        """Covers: KAL-ACC-008"""
        pko = await books.account("PKO Main", "1000.00")
        await books.expense(pko, "150.00")
        assert await books.balance(pko) == Decimal("850.00")

        await books.accounts.update(pko, AccountUpdate(balance=Decimal("900.00")))
        assert await books.balance(pko) == Decimal("900.00")

        await books.expense(pko, "100.00")
        assert await books.balance(pko) == Decimal("800.00")


class TestBalances:
    async def test_an_account_without_rows_holds_its_opening_balance(self, books: _Books) -> None:
        cash = await books.account("Gotówka", "300.00")
        assert await books.accounts.balances() == {cash: Decimal("300.00")}

    async def test_as_of_cuts_the_ledger_off_at_that_day(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        await books.expense(pko, "200.00", day=DAY)
        await books.expense(pko, "50.00", day=DAY + datetime.timedelta(days=1))
        assert await books.accounts.balance(pko, as_of=DAY) == Decimal("800.00")

    async def test_a_future_dated_row_counts_toward_the_current_balance(
        self, books: _Books
    ) -> None:
        pko = await books.account("PKO Main", "1000.00")
        await books.expense(pko, "200.00", day=datetime.date.today() + datetime.timedelta(days=30))
        assert await books.balance(pko) == Decimal("800.00")

    async def test_split_parts_are_not_added_on_top_of_the_row(
        self, books: _Books, session: AsyncSession
    ) -> None:
        pko = await books.account("PKO Main", "1000.00")
        await books.txs.create(
            TransactionCreate.model_validate(
                {
                    "account_id": pko,
                    "amount": Decimal("120.00"),
                    "type": TransactionType.EXPENSE,
                    "date": DAY,
                    "is_split": True,
                    "splits": [
                        {"category_id": books.food, "amount": Decimal("100.00")},
                        {"category_id": books.food, "amount": Decimal("20.00")},
                    ],
                }
            )
        )
        assert await books.balance(pko) == Decimal("880.00")

    async def test_the_breakdown_card_reads_derived_balances(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        await books.expense(pko, "250.00")
        breakdown = await books.accounts.balance_breakdown()
        assert [(a.name, a.balance) for a in breakdown.shown] == [("PKO Main", Decimal("750.00"))]

    async def test_setting_the_balance_leaves_the_transactions_alone(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        expense = await books.expense(pko, "150.00")
        await books.accounts.update(pko, AccountUpdate(balance=Decimal("900.00")))
        row = await books.txs.get(expense)
        assert row is not None
        assert row.amount == Decimal("150.00")


class TestEditedBalance:
    def test_an_untouched_figure_is_not_sent(self) -> None:
        assert AccountService.edited_balance(Decimal("850.00"), 850.0) is None

    def test_a_changed_figure_is_sent_to_the_grosz(self) -> None:
        assert AccountService.edited_balance(Decimal("850.00"), 900.004) == Decimal("900.00")

    def test_an_empty_field_is_not_sent(self) -> None:
        assert AccountService.edited_balance(Decimal("850.00"), None) is None


class TestTransferDirection:
    async def test_create_transfer_orients_legs_by_position(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        savings = await books.account("Oszczędności", "0.00")
        # Payload directions deliberately swapped: position decides.
        out, incoming = await books.txs.create_transfer(
            TransactionCreate(
                account_id=pko,
                amount=Decimal("500.00"),
                type=TransactionType.TRANSFER,
                transfer_direction=TransferDirection.IN,
                date=DAY,
                is_internal_transfer=True,
            ),
            TransactionCreate(
                account_id=savings,
                amount=Decimal("500.00"),
                type=TransactionType.TRANSFER,
                transfer_direction=TransferDirection.OUT,
                date=DAY,
                is_internal_transfer=True,
            ),
        )
        assert out.transfer_direction == TransferDirection.OUT
        assert incoming.transfer_direction == TransferDirection.IN

    async def test_pairing_keeps_both_balances(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        savings = await books.account("Oszczędności", "0.00")
        # The income is written first, so it has the lower id: pairing must
        # not fall back on id order.
        income = await books.income(savings, "300.00")
        expense = await books.expense(pko, "300.00")
        await books.txs.pair_as_transfer(expense, income)
        assert await books.balance(pko) == Decimal("700.00")
        assert await books.balance(savings) == Decimal("300.00")
        out_row = await books.txs.get(expense)
        in_row = await books.txs.get(income)
        assert out_row is not None and in_row is not None
        assert out_row.transfer_direction == TransferDirection.OUT
        assert in_row.transfer_direction == TransferDirection.IN

    async def test_an_expense_edited_into_a_transfer_keeps_its_balance(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        expense = await books.expense(pko, "200.00")
        updated = await books.txs.update(
            expense, TransactionUpdate(type=TransactionType.TRANSFER, category_id=None)
        )
        assert updated is not None
        assert updated.transfer_direction == TransferDirection.OUT
        assert await books.balance(pko) == Decimal("800.00")

    async def test_a_transfer_edited_into_an_income_loses_its_direction(
        self, books: _Books
    ) -> None:
        pko = await books.account("PKO Main", "1000.00")
        savings = await books.account("Oszczędności", "0.00")
        _, incoming = await books.transfer(pko, savings, "500.00")
        updated = await books.txs.update(
            incoming, TransactionUpdate(type=TransactionType.INCOME, category_id=books.salary)
        )
        assert updated is not None
        assert updated.transfer_direction is None
        assert await books.balance(savings) == Decimal("500.00")

    async def test_a_directionless_transfer_edit_is_refused(self, books: _Books) -> None:
        pko = await books.account("PKO Main", "1000.00")
        savings = await books.account("Oszczędności", "0.00")
        out, _ = await books.transfer(pko, savings, "500.00")
        row = await books.txs.get(out)
        assert row is not None
        row.transfer_direction = None
        with pytest.raises(ValidationError):
            TransactionService._settle_transfer_direction(row, TransactionType.TRANSFER)

    def test_the_schema_requires_a_direction_on_a_transfer(self) -> None:
        with pytest.raises(PydanticValidationError, match="transfer_direction"):
            TransactionCreate(
                account_id=1,
                amount=Decimal("10.00"),
                type=TransactionType.TRANSFER,
                date=DAY,
            )

    def test_the_schema_refuses_a_direction_on_an_expense(self) -> None:
        with pytest.raises(PydanticValidationError, match="transfer_direction"):
            TransactionCreate(
                account_id=1,
                category_id=1,
                amount=Decimal("10.00"),
                type=TransactionType.EXPENSE,
                transfer_direction=TransferDirection.OUT,
                date=DAY,
            )

    async def test_the_database_refuses_a_transfer_without_direction(
        self, books: _Books, session: AsyncSession
    ) -> None:
        pko = await books.account("PKO Main", "1000.00")
        session.add(
            Transaction(
                account_id=pko,
                amount=Decimal("10.00"),
                type=TransactionType.TRANSFER,
                date=DAY,
            )
        )
        with pytest.raises(IntegrityError, match="ck_transactions_transfer_direction"):
            await session.flush()
        await session.rollback()

    async def test_a_posted_planned_transfer_leaves_its_account(
        self, books: _Books, session: AsyncSession
    ) -> None:
        pko = await books.account("PKO Main", "1000.00")
        planned_svc = PlannedTransactionService(session)
        planned = await planned_svc.create(
            PlannedTransactionCreate(
                name="Pensja dla siebie",
                amount=Decimal("400.00"),
                type=TransactionType.TRANSFER,
                account_id=pko,
                frequency=RecurrenceFrequency.ONCE,
                start_date=DAY,
            )
        )
        posted = await planned_svc.post_occurrence(planned.id, DAY)
        assert posted.transfer_direction == TransferDirection.OUT
        assert await books.balance(pko) == Decimal("600.00")
