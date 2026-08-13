# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for AccountService — uses in-memory SQLite."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.schemas.account import AccountCreate, AccountUpdate
from kaleta.services import AccountService

SQL_INJECTION_NAMES = [
    "'; DROP TABLE accounts; --",
    "' OR '1'='1",
    "UNION SELECT * FROM accounts--",
    "admin'--",
]


@pytest.fixture
def svc(session: AsyncSession) -> AccountService:
    return AccountService(session)


class TestAccountServiceCreate:
    async def test_create_returns_account_with_id(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Test", type=AccountType.CHECKING))
        assert account.id is not None
        assert account.name == "Test"

    async def test_create_sets_defaults(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Test"))
        assert account.balance == Decimal("0.00")
        assert account.type == AccountType.CHECKING

    async def test_create_preserves_all_fields(self, svc: AccountService):
        account = await svc.create(
            AccountCreate(name="Savings", type=AccountType.SAVINGS, balance=Decimal("1234.56"))
        )
        assert account.name == "Savings"
        assert account.type == AccountType.SAVINGS
        assert account.balance == Decimal("1234.56")

    @pytest.mark.parametrize("payload", SQL_INJECTION_NAMES)
    async def test_sql_injection_name_stored_verbatim(self, svc: AccountService, payload: str):
        """ORM parameterises queries — injection string is stored as plain text."""
        account = await svc.create(AccountCreate(name=payload[:100]))
        fetched = await svc.get(account.id)
        assert fetched is not None
        assert fetched.name == payload[:100]

    async def test_xss_name_stored_verbatim(self, svc: AccountService):
        payload = "<script>alert('xss')</script>"
        account = await svc.create(AccountCreate(name=payload[:100]))
        fetched = await svc.get(account.id)
        assert fetched is not None
        assert fetched.name == payload[:100]


class TestAccountServiceRead:
    async def test_get_nonexistent_returns_none(self, svc: AccountService):
        result = await svc.get(99999)
        assert result is None

    async def test_list_returns_all(self, svc: AccountService):
        await svc.create(AccountCreate(name="A"))
        await svc.create(AccountCreate(name="B"))
        accounts = await svc.list()
        assert len(accounts) == 2

    async def test_list_ordered_by_name(self, svc: AccountService):
        await svc.create(AccountCreate(name="Zebra"))
        await svc.create(AccountCreate(name="Alpha"))
        accounts = await svc.list()
        assert accounts[0].name == "Alpha"
        assert accounts[1].name == "Zebra"


class TestAccountServiceUpdate:
    async def test_update_name(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Old"))
        updated = await svc.update(account.id, AccountUpdate(name="New"))
        assert updated is not None
        assert updated.name == "New"

    async def test_update_nonexistent_returns_none(self, svc: AccountService):
        result = await svc.update(99999, AccountUpdate(name="x"))
        assert result is None

    async def test_update_only_provided_fields(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Test", type=AccountType.SAVINGS))
        updated = await svc.update(account.id, AccountUpdate(name="New Name"))
        assert updated is not None
        assert updated.type == AccountType.SAVINGS  # unchanged


class TestAccountServiceDelete:
    async def test_delete_existing(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="To Delete"))
        result = await svc.delete(account.id)
        assert result is True
        assert await svc.get(account.id) is None

    async def test_delete_nonexistent_returns_false(self, svc: AccountService):
        result = await svc.delete(99999)
        assert result is False


class TestAccountServiceAdjustBalance:
    async def test_adjust_balance_positive(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Test", balance=Decimal("100.00")))
        await svc.adjust_balance(account.id, Decimal("50.00"))
        updated = await svc.get(account.id)
        assert updated is not None
        assert updated.balance == Decimal("150.00")

    async def test_adjust_balance_negative(self, svc: AccountService):
        account = await svc.create(AccountCreate(name="Test", balance=Decimal("100.00")))
        await svc.adjust_balance(account.id, Decimal("-30.00"))
        updated = await svc.get(account.id)
        assert updated is not None
        assert updated.balance == Decimal("70.00")


class TestAccountServiceListWithActivity:
    async def test_list_with_activity_returns_newest_date_and_last_import(
        self, session: AsyncSession, svc: AccountService
    ) -> None:
        """Covers: KAL-CSV-008, KAL-CSV-009 — activity aggregates without N+1."""
        from datetime import date

        from kaleta.models.category import CategoryType
        from kaleta.models.transaction import TransactionType
        from kaleta.schemas.category import CategoryCreate
        from kaleta.schemas.transaction import TransactionCreate
        from kaleta.services.category_service import CategoryService
        from kaleta.services.import_service import ImportService
        from kaleta.services.transaction_service import TransactionService

        loaded = await svc.create(AccountCreate(name="Loaded"))
        empty = await svc.create(AccountCreate(name="Empty"))
        category = await CategoryService(session).create(
            CategoryCreate(name="Food", type=CategoryType.EXPENSE)
        )

        await TransactionService(session).create(
            TransactionCreate(
                account_id=loaded.id,
                category_id=category.id,
                amount=Decimal("10.00"),
                type=TransactionType.EXPENSE,
                date=date(2024, 3, 10),
                description="Older",
            )
        )
        await TransactionService(session).create(
            TransactionCreate(
                account_id=loaded.id,
                category_id=category.id,
                amount=Decimal("20.00"),
                type=TransactionType.EXPENSE,
                date=date(2024, 6, 15),
                description="Newer",
            )
        )

        ImportService(session).record_import_run(
            account_id=loaded.id,
            filename="statement.csv",
            profile="generic",
            imported_count=2,
            skipped_count=0,
            row_date_min=date(2024, 3, 10),
            row_date_max=date(2024, 6, 15),
        )
        await session.commit()

        rows = await svc.list_with_activity()
        by_name = {r.name: r for r in rows}
        assert by_name["Loaded"].newest_transaction_date == date(2024, 6, 15)
        assert by_name["Loaded"].last_import_filename == "statement.csv"
        assert by_name["Loaded"].last_import_at is not None
        assert by_name["Empty"].newest_transaction_date is None
        assert by_name["Empty"].last_import_filename is None
        assert empty.id in {r.id for r in rows}

    async def test_is_stale_threshold(self) -> None:
        from datetime import date, timedelta

        from kaleta.services.account_service import STALE_ACTIVITY_DAYS

        today = date(2024, 8, 13)
        assert AccountService.is_stale(None, today=today) is True
        assert AccountService.is_stale(today - timedelta(days=STALE_ACTIVITY_DAYS + 1), today=today)
        assert not AccountService.is_stale(
            today - timedelta(days=STALE_ACTIVITY_DAYS),
            today=today,
        )
        assert not AccountService.is_stale(today, today=today)
