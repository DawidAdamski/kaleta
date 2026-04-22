"""Unit tests for TransactionService — uses in-memory SQLite."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.account import AccountType
from kaleta.models.category import CategoryType
from kaleta.models.transaction import TransactionType
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate
from kaleta.schemas.tag import TagCreate
from kaleta.schemas.transaction import TransactionCreate, TransactionSplitCreate, TransactionUpdate
from kaleta.services import AccountService, CategoryService, TagService, TransactionService

TODAY = datetime.date.today()


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> TransactionService:
    return TransactionService(session)


async def _make_account(session: AsyncSession, name: str = "Test Account") -> int:
    svc = AccountService(session)
    acc = await svc.create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_category(
    session: AsyncSession, name: str = "Food", cat_type: CategoryType = CategoryType.EXPENSE
) -> int:
    svc = CategoryService(session)
    cat = await svc.create(CategoryCreate(name=name, type=cat_type))
    return cat.id


def _tx(account_id: int, category_id: int, **kwargs) -> TransactionCreate:
    defaults = dict(
        account_id=account_id,
        category_id=category_id,
        amount=Decimal("100.00"),
        type=TransactionType.EXPENSE,
        date=TODAY,
        description="Test",
    )
    defaults.update(kwargs)
    return TransactionCreate(**defaults)


# ── Create ────────────────────────────────────────────────────────────────────


class TestTransactionCreate:
    async def test_create_expense(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        assert tx.id is not None
        assert tx.amount == Decimal("100.00")
        assert tx.type == TransactionType.EXPENSE

    async def test_create_income(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, cat_type=CategoryType.INCOME)
        tx = await svc.create(_tx(acc_id, cat_id, type=TransactionType.INCOME))
        assert tx.type == TransactionType.INCOME

    async def test_create_internal_transfer(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("500.00"),
                type=TransactionType.TRANSFER,
                date=TODAY,
                description="Transfer",
                is_internal_transfer=True,
            )
        )
        assert tx.is_internal_transfer is True
        assert tx.category_id is None

    async def test_sql_injection_description_stored_verbatim(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        payload = "'; DROP TABLE transactions; --"
        tx = await svc.create(_tx(acc_id, cat_id, description=payload))
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.description == payload

    async def test_xss_description_stored_verbatim(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        payload = "<script>alert('xss')</script>"
        tx = await svc.create(_tx(acc_id, cat_id, description=payload))
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.description == payload


# ── Read ──────────────────────────────────────────────────────────────────────


class TestTransactionRead:
    async def test_get_nonexistent_returns_none(self, svc: TransactionService):
        result = await svc.get(99999)
        assert result is None

    async def test_list_returns_most_recent_first(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=10)
        await svc.create(_tx(acc_id, cat_id, date=old_date, description="Old"))
        await svc.create(_tx(acc_id, cat_id, date=TODAY, description="New"))
        txs = await svc.list()
        assert txs[0].description == "New"

    async def test_list_filter_by_account(self, svc: TransactionService, session: AsyncSession):
        acc1_id = await _make_account(session, "Account 1")
        acc2_id = await _make_account(session, "Account 2")
        cat_id = await _make_category(session)
        await svc.create(_tx(acc1_id, cat_id, description="Acc1 tx"))
        await svc.create(_tx(acc2_id, cat_id, description="Acc2 tx"))
        txs = await svc.list(account_ids=[acc1_id])
        assert len(txs) == 1
        assert txs[0].description == "Acc1 tx"


# ── Update ────────────────────────────────────────────────────────────────────


class TestTransactionUpdate:
    async def test_update_description(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id, description="Original"))
        updated = await svc.update(tx.id, TransactionUpdate(description="Updated"))
        assert updated is not None
        assert updated.description == "Updated"

    async def test_update_amount(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        updated = await svc.update(tx.id, TransactionUpdate(amount=Decimal("999.99")))
        assert updated is not None
        assert updated.amount == Decimal("999.99")

    async def test_update_nonexistent_returns_none(self, svc: TransactionService):
        result = await svc.update(99999, TransactionUpdate(description="x"))
        assert result is None


# ── Delete ────────────────────────────────────────────────────────────────────


class TestTransactionDelete:
    async def test_delete_existing(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        assert await svc.delete(tx.id) is True
        assert await svc.get(tx.id) is None

    async def test_delete_nonexistent(self, svc: TransactionService):
        assert await svc.delete(99999) is False


# ── Tags ──────────────────────────────────────────────────────────────────────
#
# Regression coverage for the MissingGreenlet bug: assigning ``transaction.tags``
# after flush in async context used to trigger a lazy-load of the (empty)
# existing collection and blow up. These tests exercise every variant of the
# create/update tag flow so that regression cannot return silently.


async def _make_tag(session: AsyncSession, name: str) -> int:
    tag = await TagService(session).create(TagCreate(name=name))
    return tag.id


class TestTransactionTags:
    async def test_create_without_tag_ids_does_not_attach_tags(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        assert tx.tags == []

    async def test_create_with_empty_tag_ids_does_not_attach_tags(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[]))
        assert tx.tags == []

    async def test_create_with_single_tag(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tag_id = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[tag_id]))
        assert [t.name for t in tx.tags] == ["Business"]

    async def test_create_with_multiple_tags(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        t1 = await _make_tag(session, "Business")
        t2 = await _make_tag(session, "Recurring")
        t3 = await _make_tag(session, "Card")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[t1, t2, t3]))
        assert {t.name for t in tx.tags} == {"Business", "Recurring", "Card"}

    async def test_create_with_unknown_tag_id_skips_it(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        real_tag = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[real_tag, 99_999]))
        assert [t.name for t in tx.tags] == ["Business"]

    async def test_create_persists_tag_association_to_db(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tag_id = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[tag_id]))
        # Fetch a fresh copy — proves the link row is in transaction_tags.
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert [t.id for t in fetched.tags] == [tag_id]

    async def test_update_adds_tags_to_tagless_transaction(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        tag_id = await _make_tag(session, "Business")
        updated = await svc.update(tx.id, TransactionUpdate(tag_ids=[tag_id]))
        assert updated is not None
        assert [t.name for t in updated.tags] == ["Business"]

    async def test_update_replaces_existing_tags(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old = await _make_tag(session, "Business")
        new = await _make_tag(session, "Recurring")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[old]))
        updated = await svc.update(tx.id, TransactionUpdate(tag_ids=[new]))
        assert updated is not None
        assert [t.name for t in updated.tags] == ["Recurring"]

    async def test_update_to_empty_list_clears_tags(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tag_id = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[tag_id]))
        updated = await svc.update(tx.id, TransactionUpdate(tag_ids=[]))
        assert updated is not None
        assert updated.tags == []

    async def test_update_without_tag_ids_leaves_tags_untouched(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tag_id = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[tag_id]))
        updated = await svc.update(tx.id, TransactionUpdate(description="Renamed"))
        assert updated is not None
        assert [t.name for t in updated.tags] == ["Business"]
        assert updated.description == "Renamed"

    async def test_created_transaction_tags_are_eagerly_loaded(
        self, svc: TransactionService, session: AsyncSession
    ):
        """Accessing ``.tags`` on the returned instance must not trigger IO.

        If tags weren't eager-loaded on the post-commit fetch, iterating
        ``.tags`` outside the session's greenlet would raise MissingGreenlet.
        """
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tag_id = await _make_tag(session, "Business")
        tx = await svc.create(_tx(acc_id, cat_id, tag_ids=[tag_id]))
        # Touch the collection — if not eager-loaded, this would try to IO
        # synchronously and raise MissingGreenlet.
        names = [t.name for t in tx.tags]
        assert names == ["Business"]


# ── List filters ───────────────────────────────────────────────────────────────


class TestTransactionListFilters:
    async def test_filter_by_category_ids(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        await svc.create(_tx(acc_id, cat1_id, description="Grocery"))
        await svc.create(_tx(acc_id, cat2_id, description="Bus"))
        txs = await svc.list(category_ids=[cat1_id])
        assert len(txs) == 1
        assert txs[0].description == "Grocery"

    async def test_filter_by_multiple_category_ids(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        cat3_id = await _make_category(session, "Utilities")
        await svc.create(_tx(acc_id, cat1_id, description="Grocery"))
        await svc.create(_tx(acc_id, cat2_id, description="Bus"))
        await svc.create(_tx(acc_id, cat3_id, description="Electric"))
        txs = await svc.list(category_ids=[cat1_id, cat3_id])
        descriptions = {t.description for t in txs}
        assert descriptions == {"Grocery", "Electric"}

    async def test_filter_by_date_from(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=30)
        mid_date = TODAY - datetime.timedelta(days=5)
        await svc.create(_tx(acc_id, cat_id, date=old_date, description="Old"))
        await svc.create(_tx(acc_id, cat_id, date=mid_date, description="Mid"))
        await svc.create(_tx(acc_id, cat_id, date=TODAY, description="New"))
        txs = await svc.list(date_from=mid_date)
        descriptions = {t.description for t in txs}
        assert descriptions == {"Mid", "New"}
        assert "Old" not in descriptions

    async def test_filter_by_date_to(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=30)
        mid_date = TODAY - datetime.timedelta(days=5)
        await svc.create(_tx(acc_id, cat_id, date=old_date, description="Old"))
        await svc.create(_tx(acc_id, cat_id, date=mid_date, description="Mid"))
        await svc.create(_tx(acc_id, cat_id, date=TODAY, description="New"))
        txs = await svc.list(date_to=mid_date)
        descriptions = {t.description for t in txs}
        assert descriptions == {"Old", "Mid"}
        assert "New" not in descriptions

    async def test_filter_by_date_range(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=30)
        mid_date = TODAY - datetime.timedelta(days=5)
        await svc.create(_tx(acc_id, cat_id, date=old_date, description="Old"))
        await svc.create(_tx(acc_id, cat_id, date=mid_date, description="Mid"))
        await svc.create(_tx(acc_id, cat_id, date=TODAY, description="New"))
        # date_from inclusive, date_to inclusive: only "Mid"
        one_day = datetime.timedelta(days=1)
        txs = await svc.list(date_from=mid_date - one_day, date_to=mid_date + one_day)
        assert len(txs) == 1
        assert txs[0].description == "Mid"

    async def test_filter_by_tx_types_expense(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        exp_cat_id = await _make_category(session, "Food", CategoryType.EXPENSE)
        inc_cat_id = await _make_category(session, "Salary", CategoryType.INCOME)
        await svc.create(_tx(acc_id, exp_cat_id, type=TransactionType.EXPENSE, description="Lunch"))
        await svc.create(
            _tx(acc_id, inc_cat_id, type=TransactionType.INCOME, description="Paycheck")
        )
        txs = await svc.list(tx_types=[TransactionType.EXPENSE])
        assert len(txs) == 1
        assert txs[0].description == "Lunch"

    async def test_filter_by_tx_types_multiple(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        exp_cat_id = await _make_category(session, "Food", CategoryType.EXPENSE)
        inc_cat_id = await _make_category(session, "Salary", CategoryType.INCOME)
        await svc.create(_tx(acc_id, exp_cat_id, type=TransactionType.EXPENSE, description="Lunch"))
        await svc.create(
            _tx(acc_id, inc_cat_id, type=TransactionType.INCOME, description="Paycheck")
        )
        await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("200.00"),
                type=TransactionType.TRANSFER,
                date=TODAY,
                description="Transfer",
                is_internal_transfer=True,
            )
        )
        txs = await svc.list(tx_types=[TransactionType.EXPENSE, TransactionType.INCOME])
        descriptions = {t.description for t in txs}
        assert descriptions == {"Lunch", "Paycheck"}

    async def test_filter_by_search_description(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Grocery store visit"))
        await svc.create(_tx(acc_id, cat_id, description="Bus ticket"))
        txs = await svc.list(search="grocery")
        assert len(txs) == 1
        assert txs[0].description == "Grocery store visit"

    async def test_filter_search_is_case_insensitive(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Coffee shop"))
        txs = await svc.list(search="COFFEE")
        assert len(txs) == 1

    async def test_filter_search_partial_match(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Online subscription renewal"))
        txs = await svc.list(search="subscript")
        assert len(txs) == 1

    async def test_filter_search_no_match_returns_empty(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Grocery"))
        txs = await svc.list(search="zzz_no_match_zzz")
        assert txs == []

    async def test_offset_skips_rows(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        # Create 3 transactions; list() returns most-recent-first so ids are predictable by date
        date_a = TODAY - datetime.timedelta(days=2)
        date_b = TODAY - datetime.timedelta(days=1)
        date_c = TODAY
        await svc.create(_tx(acc_id, cat_id, date=date_a, description="Oldest"))
        await svc.create(_tx(acc_id, cat_id, date=date_b, description="Middle"))
        await svc.create(_tx(acc_id, cat_id, date=date_c, description="Newest"))
        # Without offset the first result is "Newest"
        page1 = await svc.list(limit=1, offset=0)
        assert page1[0].description == "Newest"
        # With offset=1 the first result is "Middle"
        page2 = await svc.list(limit=1, offset=1)
        assert page2[0].description == "Middle"
        # With offset=2 the first result is "Oldest"
        page3 = await svc.list(limit=1, offset=2)
        assert page3[0].description == "Oldest"

    async def test_combined_filters_account_and_category(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc1_id = await _make_account(session, "Acc1")
        acc2_id = await _make_account(session, "Acc2")
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        await svc.create(_tx(acc1_id, cat1_id, description="A1C1"))
        await svc.create(_tx(acc1_id, cat2_id, description="A1C2"))
        await svc.create(_tx(acc2_id, cat1_id, description="A2C1"))
        txs = await svc.list(account_ids=[acc1_id], category_ids=[cat1_id])
        assert len(txs) == 1
        assert txs[0].description == "A1C1"


# ── Count ─────────────────────────────────────────────────────────────────────


class TestTransactionCount:
    async def test_count_all(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        assert await svc.count() == 0
        await svc.create(_tx(acc_id, cat_id))
        await svc.create(_tx(acc_id, cat_id))
        assert await svc.count() == 2

    async def test_count_filter_by_account_ids(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc1_id = await _make_account(session, "Acc1")
        acc2_id = await _make_account(session, "Acc2")
        cat_id = await _make_category(session)
        await svc.create(_tx(acc1_id, cat_id))
        await svc.create(_tx(acc1_id, cat_id))
        await svc.create(_tx(acc2_id, cat_id))
        assert await svc.count(account_ids=[acc1_id]) == 2
        assert await svc.count(account_ids=[acc2_id]) == 1

    async def test_count_filter_by_category_ids(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        await svc.create(_tx(acc_id, cat1_id))
        await svc.create(_tx(acc_id, cat2_id))
        assert await svc.count(category_ids=[cat1_id]) == 1

    async def test_count_filter_by_date_from(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=30)
        await svc.create(_tx(acc_id, cat_id, date=old_date))
        await svc.create(_tx(acc_id, cat_id, date=TODAY))
        assert await svc.count(date_from=TODAY) == 1

    async def test_count_filter_by_date_to(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=30)
        await svc.create(_tx(acc_id, cat_id, date=old_date))
        await svc.create(_tx(acc_id, cat_id, date=TODAY))
        assert await svc.count(date_to=old_date) == 1

    async def test_count_filter_by_tx_types(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        exp_cat_id = await _make_category(session, "Food", CategoryType.EXPENSE)
        inc_cat_id = await _make_category(session, "Salary", CategoryType.INCOME)
        await svc.create(_tx(acc_id, exp_cat_id, type=TransactionType.EXPENSE))
        await svc.create(_tx(acc_id, inc_cat_id, type=TransactionType.INCOME))
        assert await svc.count(tx_types=[TransactionType.EXPENSE]) == 1
        assert await svc.count(tx_types=[TransactionType.INCOME]) == 1
        assert await svc.count(tx_types=[TransactionType.EXPENSE, TransactionType.INCOME]) == 2

    async def test_count_filter_by_search(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Coffee shop"))
        await svc.create(_tx(acc_id, cat_id, description="Grocery store"))
        assert await svc.count(search="coffee") == 1
        assert await svc.count(search="store") == 1
        assert await svc.count(search="GROCERY") == 1

    async def test_count_no_match_returns_zero(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id, description="Lunch"))
        assert await svc.count(search="zzz_no_match_zzz") == 0

    async def test_count_combined_filters(self, svc: TransactionService, session: AsyncSession):
        acc1_id = await _make_account(session, "Acc1")
        acc2_id = await _make_account(session, "Acc2")
        cat_id = await _make_category(session)
        old_date = TODAY - datetime.timedelta(days=10)
        await svc.create(_tx(acc1_id, cat_id, date=TODAY, description="Target"))
        await svc.create(_tx(acc1_id, cat_id, date=old_date, description="Too old"))
        await svc.create(_tx(acc2_id, cat_id, date=TODAY, description="Wrong account"))
        assert await svc.count(account_ids=[acc1_id], date_from=TODAY) == 1


# ── Split transactions ─────────────────────────────────────────────────────────


class TestSplitTransactionCreate:
    async def test_create_split_sets_is_split_flag(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(
                        category_id=cat1_id, amount=Decimal("100.00"), note="Groceries"
                    ),
                    TransactionSplitCreate(
                        category_id=cat2_id, amount=Decimal("50.00"), note="Taxi"
                    ),
                ],
            )
        )
        assert tx.is_split is True
        assert tx.category_id is None

    async def test_create_split_persists_split_rows(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(
                        category_id=cat1_id, amount=Decimal("100.00"), note="Groceries"
                    ),
                    TransactionSplitCreate(
                        category_id=cat2_id, amount=Decimal("50.00"), note="Taxi"
                    ),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert len(fetched.splits) == 2

    async def test_create_split_correct_amounts(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(
                        category_id=cat1_id, amount=Decimal("100.00"), note="Groceries"
                    ),
                    TransactionSplitCreate(
                        category_id=cat2_id, amount=Decimal("50.00"), note="Taxi"
                    ),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        amounts = {s.amount for s in fetched.splits}
        assert amounts == {Decimal("100.00"), Decimal("50.00")}

    async def test_create_split_correct_notes(self, svc: TransactionService, session: AsyncSession):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(
                        category_id=cat_id, amount=Decimal("100.00"), note="Special note"
                    ),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.splits[0].note == "Special note"

    async def test_create_split_correct_category_ids(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat1_id, amount=Decimal("100.00")),
                    TransactionSplitCreate(category_id=cat2_id, amount=Decimal("50.00")),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        cat_ids = {s.category_id for s in fetched.splits}
        assert cat_ids == {cat1_id, cat2_id}

    async def test_create_split_transaction_id_on_split_rows(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.splits[0].transaction_id == tx.id

    async def test_create_split_default_note_is_empty_string(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.splits[0].note == ""

    async def test_create_single_split_is_allowed(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("75.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("75.00")),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert len(fetched.splits) == 1


# ── Split transactions — get() eager-loads splits ─────────────────────────────


class TestSplitTransactionGet:
    async def test_get_loads_splits_relationship(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(
                        category_id=cat_id, amount=Decimal("100.00"), note="Lunch"
                    ),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        # Splits must be accessible without triggering lazy-load errors
        assert len(fetched.splits) == 1
        assert fetched.splits[0].note == "Lunch"

    async def test_get_non_split_has_empty_splits(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        tx = await svc.create(_tx(acc_id, cat_id))
        fetched = await svc.get(tx.id)
        assert fetched is not None
        assert fetched.splits == []

    async def test_get_split_loads_split_category(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Groceries")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                ],
            )
        )
        fetched = await svc.get(tx.id)
        assert fetched is not None
        split = fetched.splits[0]
        # category relationship on the split must be eager-loaded
        assert split.category is not None
        assert split.category.name == "Groceries"


# ── Split transactions — list() eager-loads splits ────────────────────────────


class TestSplitTransactionList:
    async def test_list_includes_splits_for_split_transactions(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat1_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat1_id, amount=Decimal("100.00")),
                    TransactionSplitCreate(category_id=cat2_id, amount=Decimal("50.00")),
                ],
            )
        )
        txs = await svc.list()
        assert len(txs) == 1
        assert len(txs[0].splits) == 2

    async def test_list_non_split_transactions_have_empty_splits(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session)
        await svc.create(_tx(acc_id, cat_id))
        txs = await svc.list()
        assert len(txs) == 1
        assert txs[0].splits == []

    async def test_list_mixed_split_and_normal_transactions(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        cat2_id = await _make_category(session, "Transport")
        # Normal transaction
        await svc.create(_tx(acc_id, cat_id, description="Normal"))
        # Split transaction
        await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("150.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                description="Split",
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                    TransactionSplitCreate(category_id=cat2_id, amount=Decimal("50.00")),
                ],
            )
        )
        txs = await svc.list()
        by_desc = {t.description: t for t in txs}
        assert len(by_desc["Normal"].splits) == 0
        assert len(by_desc["Split"].splits) == 2

    async def test_list_split_loads_split_category(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Groceries")
        await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                ],
            )
        )
        txs = await svc.list()
        assert len(txs) == 1
        split = txs[0].splits[0]
        assert split.category is not None
        assert split.category.name == "Groceries"


# ── Split cascades on delete ───────────────────────────────────────────────────


class TestSplitTransactionDelete:
    async def test_delete_split_transaction_removes_splits(
        self, svc: TransactionService, session: AsyncSession
    ):
        acc_id = await _make_account(session)
        cat_id = await _make_category(session, "Food")
        tx = await svc.create(
            TransactionCreate(
                account_id=acc_id,
                category_id=None,
                amount=Decimal("100.00"),
                type=TransactionType.EXPENSE,
                date=TODAY,
                is_split=True,
                splits=[
                    TransactionSplitCreate(category_id=cat_id, amount=Decimal("100.00")),
                ],
            )
        )
        tx_id = tx.id
        assert await svc.delete(tx_id) is True
        assert await svc.get(tx_id) is None


# ── create_transfer() ─────────────────────────────────────────────────────────


def _transfer_leg(account_id: int, amount: Decimal, **kwargs) -> TransactionCreate:
    defaults = dict(
        account_id=account_id,
        category_id=None,
        amount=amount,
        type=TransactionType.TRANSFER,
        date=TODAY,
        description="Transfer",
        is_internal_transfer=True,
    )
    defaults.update(kwargs)
    return TransactionCreate(**defaults)


class TestCreateTransfer:
    async def test_create_transfer_returns_two_transactions(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-200.00")),
            _transfer_leg(dst_id, Decimal("200.00")),
        )
        assert tx_out.id is not None
        assert tx_in.id is not None

    async def test_create_transfer_legs_are_linked_to_each_other(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-500.00")),
            _transfer_leg(dst_id, Decimal("500.00")),
        )
        assert tx_out.linked_transaction_id == tx_in.id
        assert tx_in.linked_transaction_id == tx_out.id

    async def test_create_transfer_outgoing_leg_has_source_account(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, _ = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-100.00")),
            _transfer_leg(dst_id, Decimal("100.00")),
        )
        assert tx_out.account_id == src_id

    async def test_create_transfer_incoming_leg_has_destination_account(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        _, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-100.00")),
            _transfer_leg(dst_id, Decimal("100.00")),
        )
        assert tx_in.account_id == dst_id

    async def test_create_transfer_both_legs_are_internal_transfers(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-300.00")),
            _transfer_leg(dst_id, Decimal("300.00")),
        )
        assert tx_out.is_internal_transfer is True
        assert tx_in.is_internal_transfer is True

    async def test_create_transfer_both_legs_have_transfer_type(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-150.00")),
            _transfer_leg(dst_id, Decimal("150.00")),
        )
        assert tx_out.type == TransactionType.TRANSFER
        assert tx_in.type == TransactionType.TRANSFER

    async def test_create_transfer_both_legs_persisted_to_db(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-250.00")),
            _transfer_leg(dst_id, Decimal("250.00")),
        )
        fetched_out = await svc.get(tx_out.id)
        fetched_in = await svc.get(tx_in.id)
        assert fetched_out is not None
        assert fetched_in is not None

    async def test_create_transfer_with_exchange_rate_same_on_both_legs(
        self, svc: TransactionService, session: AsyncSession
    ):
        """Cross-currency transfer: both legs carry the same exchange_rate."""
        src_id = await _make_account(session, "PLN Account")
        dst_id = await _make_account(session, "EUR Account")
        rate = Decimal("4.25")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-425.00"), exchange_rate=rate),
            _transfer_leg(dst_id, Decimal("100.00"), exchange_rate=rate),
        )
        assert tx_out.exchange_rate == rate
        assert tx_in.exchange_rate == rate

    async def test_create_transfer_without_exchange_rate_defaults_none(
        self, svc: TransactionService, session: AsyncSession
    ):
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-100.00")),
            _transfer_leg(dst_id, Decimal("100.00")),
        )
        assert tx_out.exchange_rate is None
        assert tx_in.exchange_rate is None

    async def test_create_transfer_linked_ids_fetched_from_db(
        self, svc: TransactionService, session: AsyncSession
    ):
        """Verify link integrity survives a round-trip through the database."""
        src_id = await _make_account(session, "Source")
        dst_id = await _make_account(session, "Destination")
        tx_out, tx_in = await svc.create_transfer(
            _transfer_leg(src_id, Decimal("-200.00")),
            _transfer_leg(dst_id, Decimal("200.00")),
        )
        fetched_out = await svc.get(tx_out.id)
        fetched_in = await svc.get(tx_in.id)
        assert fetched_out is not None
        assert fetched_in is not None
        assert fetched_out.linked_transaction_id == tx_in.id
        assert fetched_in.linked_transaction_id == tx_out.id
