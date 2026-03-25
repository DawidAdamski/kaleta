"""Unit tests for PayeeService — uses in-memory SQLite."""

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
from kaleta.schemas.payee import PayeeCreate, PayeeUpdate
from kaleta.schemas.transaction import TransactionCreate
from kaleta.services import AccountService, CategoryService, PayeeService, TransactionService

TODAY = datetime.date.today()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _make_account(session: AsyncSession, name: str = "Checking") -> int:
    svc = AccountService(session)
    acc = await svc.create(AccountCreate(name=name, type=AccountType.CHECKING))
    return acc.id


async def _make_category(session: AsyncSession, name: str = "Misc") -> int:
    svc = CategoryService(session)
    cat = await svc.create(CategoryCreate(name=name, type=CategoryType.EXPENSE))
    return cat.id


async def _make_payee(session: AsyncSession, name: str) -> int:
    svc = PayeeService(session)
    payee = await svc.create(PayeeCreate(name=name))
    return payee.id


async def _make_transaction(
    session: AsyncSession,
    account_id: int,
    category_id: int,
    payee_id: int | None = None,
    description: str = "Test",
) -> int:
    svc = TransactionService(session)
    tx = await svc.create(
        TransactionCreate(
            account_id=account_id,
            category_id=category_id,
            payee_id=payee_id,
            amount=Decimal("50.00"),
            type=TransactionType.EXPENSE,
            date=TODAY,
            description=description,
        )
    )
    return tx.id


# ── Basic CRUD ────────────────────────────────────────────────────────────────


@pytest.fixture
def svc(session: AsyncSession) -> PayeeService:
    return PayeeService(session)


class TestPayeeCreate:

    async def test_create_returns_payee_with_id(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="Biedronka"))
        assert payee.id is not None
        assert payee.name == "Biedronka"

    async def test_create_with_notes(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="Lidl", notes="Discount supermarket"))
        assert payee.notes == "Discount supermarket"

    async def test_create_sql_injection_stored_verbatim(self, svc: PayeeService):
        payload = "'; DROP TABLE payees; --"
        payee = await svc.create(PayeeCreate(name=payload))
        fetched = await svc.get(payee.id)
        assert fetched is not None
        assert fetched.name == payload

    async def test_create_with_all_new_fields(self, svc: PayeeService):
        payee = await svc.create(
            PayeeCreate(
                name="Biedronka HQ",
                website="https://biedronka.pl",
                address="ul. Kwiatowa 1",
                city="Poznań",
                country="Poland",
                email="kontakt@biedronka.pl",
                phone="+48 61 123 45 67",
            )
        )
        assert payee.id is not None
        assert payee.website == "https://biedronka.pl"
        assert payee.address == "ul. Kwiatowa 1"
        assert payee.city == "Poznań"
        assert payee.country == "Poland"
        assert payee.email == "kontakt@biedronka.pl"
        assert payee.phone == "+48 61 123 45 67"

    async def test_new_fields_default_to_none(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="NullFieldsPayee"))
        assert payee.website is None
        assert payee.address is None
        assert payee.city is None
        assert payee.country is None
        assert payee.email is None
        assert payee.phone is None

    async def test_new_fields_round_trip_via_get(self, svc: PayeeService):
        """Values written on create must survive a database round-trip."""
        payee = await svc.create(
            PayeeCreate(
                name="RoundTrip",
                website="https://example.com",
                address="Main St 42",
                city="Warsaw",
                country="Poland",
                email="hello@example.com",
                phone="123456789",
            )
        )
        fetched = await svc.get(payee.id)
        assert fetched is not None
        assert fetched.website == "https://example.com"
        assert fetched.address == "Main St 42"
        assert fetched.city == "Warsaw"
        assert fetched.country == "Poland"
        assert fetched.email == "hello@example.com"
        assert fetched.phone == "123456789"


class TestPayeeRead:

    async def test_get_returns_correct_payee(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="Żabka"))
        fetched = await svc.get(payee.id)
        assert fetched is not None
        assert fetched.id == payee.id

    async def test_get_nonexistent_returns_none(self, svc: PayeeService):
        assert await svc.get(99999) is None

    async def test_list_returns_all_ordered_by_name(self, svc: PayeeService):
        await svc.create(PayeeCreate(name="Żabka"))
        await svc.create(PayeeCreate(name="Biedronka"))
        await svc.create(PayeeCreate(name="Lidl"))
        payees = await svc.list()
        names = [p.name for p in payees]
        assert names == sorted(names)


class TestPayeeUpdate:

    async def test_update_name(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="Old Name"))
        updated = await svc.update(payee.id, PayeeUpdate(name="New Name"))
        assert updated is not None
        assert updated.name == "New Name"

    async def test_update_nonexistent_returns_none(self, svc: PayeeService):
        assert await svc.update(99999, PayeeUpdate(name="x")) is None

    async def test_update_new_fields(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="UpdateTarget"))
        updated = await svc.update(
            payee.id,
            PayeeUpdate(
                website="https://updated.com",
                address="New St 99",
                city="Kraków",
                country="Poland",
                email="new@updated.com",
                phone="987654321",
            ),
        )
        assert updated is not None
        assert updated.website == "https://updated.com"
        assert updated.address == "New St 99"
        assert updated.city == "Kraków"
        assert updated.country == "Poland"
        assert updated.email == "new@updated.com"
        assert updated.phone == "987654321"

    async def test_update_new_fields_partial_leaves_others_unchanged(self, svc: PayeeService):
        payee = await svc.create(
            PayeeCreate(
                name="PartialUpdate",
                city="Gdańsk",
                country="Poland",
                email="keep@me.com",
            )
        )
        updated = await svc.update(payee.id, PayeeUpdate(city="Wrocław"))
        assert updated is not None
        assert updated.city == "Wrocław"
        assert updated.country == "Poland"
        assert updated.email == "keep@me.com"

    async def test_update_new_fields_round_trip_via_get(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="UpdateRoundTrip"))
        await svc.update(payee.id, PayeeUpdate(website="https://rt.com", phone="+1 555 000"))
        fetched = await svc.get(payee.id)
        assert fetched is not None
        assert fetched.website == "https://rt.com"
        assert fetched.phone == "+1 555 000"


class TestPayeeDelete:

    async def test_delete_existing(self, svc: PayeeService):
        payee = await svc.create(PayeeCreate(name="ToDelete"))
        assert await svc.delete(payee.id) is True
        assert await svc.get(payee.id) is None

    async def test_delete_nonexistent(self, svc: PayeeService):
        assert await svc.delete(99999) is False


# ── merge() ───────────────────────────────────────────────────────────────────


class TestPayeeMerge:

    async def test_merge_reassigns_transactions_to_keep(self, session: AsyncSession):
        """Transactions that belonged to merged payees must point to keep_id afterwards."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)

        keep_id = await _make_payee(session, "Keep")
        merge1_id = await _make_payee(session, "Merge1")
        merge2_id = await _make_payee(session, "Merge2")

        tx1_id = await _make_transaction(session, account_id, cat_id, payee_id=merge1_id)
        tx2_id = await _make_transaction(session, account_id, cat_id, payee_id=merge2_id)

        deleted = await payee_svc.merge(keep_id, [merge1_id, merge2_id])

        assert deleted == 2

        # expire the session identity map so SQLAlchemy re-fetches from the DB
        session.expire_all()
        tx_svc = TransactionService(session)
        tx1 = await tx_svc.get(tx1_id)
        tx2 = await tx_svc.get(tx2_id)
        assert tx1 is not None and tx1.payee_id == keep_id
        assert tx2 is not None and tx2.payee_id == keep_id

    async def test_merge_deletes_merged_payees(self, session: AsyncSession):
        """Merged payees must not exist after the operation."""
        payee_svc = PayeeService(session)

        keep_id = await _make_payee(session, "Keep")
        merge1_id = await _make_payee(session, "Merge1")
        merge2_id = await _make_payee(session, "Merge2")

        await payee_svc.merge(keep_id, [merge1_id, merge2_id])

        assert await payee_svc.get(merge1_id) is None
        assert await payee_svc.get(merge2_id) is None

    async def test_merge_keep_payee_survives(self, session: AsyncSession):
        """The keep payee must still exist after the merge."""
        payee_svc = PayeeService(session)

        keep_id = await _make_payee(session, "Keep")
        merge_id = await _make_payee(session, "Merge")

        await payee_svc.merge(keep_id, [merge_id])

        keep = await payee_svc.get(keep_id)
        assert keep is not None
        assert keep.id == keep_id

    async def test_merge_returns_count_of_deleted_payees(self, session: AsyncSession):
        payee_svc = PayeeService(session)

        keep_id = await _make_payee(session, "Keep")
        ids = [await _make_payee(session, f"Payee{i}") for i in range(3)]

        deleted = await payee_svc.merge(keep_id, ids)
        assert deleted == 3

    async def test_merge_empty_list_returns_zero(self, session: AsyncSession):
        payee_svc = PayeeService(session)
        keep_id = await _make_payee(session, "Keep")

        deleted = await payee_svc.merge(keep_id, [])
        assert deleted == 0
        assert await payee_svc.get(keep_id) is not None

    async def test_merge_nonexistent_ids_skipped(self, session: AsyncSession):
        """Merge IDs that don't exist contribute 0 to the deleted count."""
        payee_svc = PayeeService(session)
        keep_id = await _make_payee(session, "Keep")

        deleted = await payee_svc.merge(keep_id, [88888, 99999])
        assert deleted == 0

    async def test_merge_transactions_without_payee_unaffected(self, session: AsyncSession):
        """Transactions with no payee (payee_id=None) are not affected by the merge."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)

        keep_id = await _make_payee(session, "Keep")
        merge_id = await _make_payee(session, "Merge")

        # transaction with no payee
        no_payee_tx_id = await _make_transaction(session, account_id, cat_id, payee_id=None)

        await payee_svc.merge(keep_id, [merge_id])

        session.expire_all()
        tx_svc = TransactionService(session)
        no_payee_tx = await tx_svc.get(no_payee_tx_id)
        assert no_payee_tx is not None
        assert no_payee_tx.payee_id is None

    async def test_merge_multiple_transactions_per_payee(self, session: AsyncSession):
        """All transactions belonging to a merged payee are reassigned — not just the first."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)

        keep_id = await _make_payee(session, "Keep")
        merge_id = await _make_payee(session, "Merge")

        tx_ids = [
            await _make_transaction(
                session, account_id, cat_id, payee_id=merge_id, description=f"tx{i}"
            )
            for i in range(5)
        ]

        await payee_svc.merge(keep_id, [merge_id])

        session.expire_all()
        tx_svc = TransactionService(session)
        for tx_id in tx_ids:
            tx = await tx_svc.get(tx_id)
            assert tx is not None and tx.payee_id == keep_id


# ── list_with_counts() ────────────────────────────────────────────────────────


class TestPayeeListWithCounts:

    async def test_returns_tuples_of_payee_and_count(self, session: AsyncSession):
        payee_svc = PayeeService(session)
        await _make_payee(session, "Alpha")
        rows = await payee_svc.list_with_counts()
        assert len(rows) >= 1
        payee, count = rows[0]
        assert hasattr(payee, "id")
        assert isinstance(count, int)

    async def test_count_reflects_transaction_count(self, session: AsyncSession):
        """A payee linked to 3 transactions must show count=3."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)
        payee_id = await _make_payee(session, "BusyPayee")

        for i in range(3):
            await _make_transaction(
                session, account_id, cat_id, payee_id=payee_id, description=f"tx{i}"
            )

        rows = await payee_svc.list_with_counts()
        counts = {p.name: c for p, c in rows}
        assert counts["BusyPayee"] == 3

    async def test_payee_with_no_transactions_has_count_zero(self, session: AsyncSession):
        payee_svc = PayeeService(session)
        await _make_payee(session, "EmptyPayee")

        rows = await payee_svc.list_with_counts()
        counts = {p.name: c for p, c in rows}
        assert counts["EmptyPayee"] == 0

    async def test_multiple_payees_independent_counts(self, session: AsyncSession):
        """Each payee's count is independent — transactions assigned to one don't count for another."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)

        payee_a_id = await _make_payee(session, "PayeeA")
        payee_b_id = await _make_payee(session, "PayeeB")

        # 2 transactions for A, 4 for B
        for i in range(2):
            await _make_transaction(
                session, account_id, cat_id, payee_id=payee_a_id, description=f"a{i}"
            )
        for i in range(4):
            await _make_transaction(
                session, account_id, cat_id, payee_id=payee_b_id, description=f"b{i}"
            )

        rows = await payee_svc.list_with_counts()
        counts = {p.name: c for p, c in rows}
        assert counts["PayeeA"] == 2
        assert counts["PayeeB"] == 4

    async def test_results_ordered_by_name(self, session: AsyncSession):
        payee_svc = PayeeService(session)
        for name in ["Żabka", "Biedronka", "Lidl", "Auchan"]:
            await _make_payee(session, name)

        rows = await payee_svc.list_with_counts()
        names = [p.name for p, _ in rows]
        assert names == sorted(names)

    async def test_empty_database_returns_empty_list(self, session: AsyncSession):
        payee_svc = PayeeService(session)
        rows = await payee_svc.list_with_counts()
        assert rows == []

    async def test_count_updates_after_merge(self, session: AsyncSession):
        """After merging, the keep payee's count equals the combined transaction total."""
        payee_svc = PayeeService(session)
        account_id = await _make_account(session)
        cat_id = await _make_category(session)

        keep_id = await _make_payee(session, "Keep")
        merge_id = await _make_payee(session, "Merge")

        for i in range(2):
            await _make_transaction(
                session, account_id, cat_id, payee_id=keep_id, description=f"keep{i}"
            )
        for i in range(3):
            await _make_transaction(
                session, account_id, cat_id, payee_id=merge_id, description=f"merge{i}"
            )

        await payee_svc.merge(keep_id, [merge_id])

        rows = await payee_svc.list_with_counts()
        counts = {p.name: c for p, c in rows}
        assert counts["Keep"] == 5
        assert "Merge" not in counts
