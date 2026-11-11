# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for GiftService: the yearly people-by-occasions grid."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.schemas.account import AccountCreate
from kaleta.schemas.category import CategoryCreate, CategoryType
from kaleta.schemas.gift import GiftCellSet, GiftGrid, GiftName
from kaleta.schemas.transaction import TransactionCreate, TransactionType
from kaleta.services import (
    AccountService,
    CategoryService,
    GiftService,
    TransactionService,
)


@pytest.fixture
def svc(session: AsyncSession) -> GiftService:
    return GiftService(session)


async def _expense(
    session: AsyncSession, amount: str, *, kind: TransactionType | None = None
) -> int:
    """A standalone transaction (expense unless told otherwise); returns its id."""
    tx_type = kind or TransactionType.EXPENSE
    cat_type = CategoryType.INCOME if tx_type is TransactionType.INCOME else CategoryType.EXPENSE
    account = await AccountService(session).create(
        AccountCreate(name="Konto", balance=Decimal("0.00"))
    )
    category = await CategoryService(session).create(
        CategoryCreate(name=f"Prezenty {amount}", type=cat_type)
    )
    tx = await TransactionService(session).create(
        TransactionCreate(
            account_id=account.id,
            category_id=category.id,
            amount=Decimal(amount),
            type=tx_type,
            date=datetime.date(2026, 6, 1),
            description="Gift purchase",
        )
    )
    return tx.id


YEAR = 2026


async def _lanes(svc: GiftService, people: list[str], occasions: list[str]) -> dict[str, int]:
    """Add people and occasions; return name → id for both."""
    ids: dict[str, int] = {}
    for name in people:
        ids[name] = (await svc.add_person(GiftName(name=name))).id
    for name in occasions:
        ids[name] = (await svc.add_occasion(GiftName(name=name))).id
    return ids


async def _set(
    svc: GiftService,
    ids: dict[str, int],
    person: str,
    occasion: str,
    amount: str | None,
    *,
    year: int = YEAR,
    note: str | None = None,
) -> int | None:
    cell = await svc.set_cell(
        year,
        ids[person],
        ids[occasion],
        GiftCellSet(amount=Decimal(amount) if amount is not None else None, note=note),
    )
    return cell.id if cell is not None else None


def _cell(grid: GiftGrid, ids: dict[str, int], person: str, occasion: str):
    return next(
        c for c in grid.cells if c.person_id == ids[person] and c.occasion_id == ids[occasion]
    )


class TestGrid:
    async def test_totals_per_row_column_and_year(self, svc: GiftService):
        """Covers: KAL-GFT-001 — the BDD literals."""
        ids = await _lanes(svc, ["Mama", "Tata"], ["Urodziny", "Boże Narodzenie"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00")
        await _set(svc, ids, "Mama", "Boże Narodzenie", "150.00")
        await _set(svc, ids, "Tata", "Boże Narodzenie", "100.00")

        grid = await svc.grid(YEAR)
        assert [p.name for p in grid.people] == ["Mama", "Tata"]
        assert [o.name for o in grid.occasions] == ["Urodziny", "Boże Narodzenie"]
        assert grid.row_totals == {ids["Mama"]: Decimal("350.00"), ids["Tata"]: Decimal("100.00")}
        assert grid.column_totals == {
            ids["Urodziny"]: Decimal("200.00"),
            ids["Boże Narodzenie"]: Decimal("250.00"),
        }
        assert grid.total == Decimal("450.00")

    async def test_a_person_without_cells_is_a_row_of_zeros(self, svc: GiftService):
        ids = await _lanes(svc, ["Ania"], ["Imieniny"])
        grid = await svc.grid(YEAR)
        assert grid.cells == []
        assert grid.row_totals == {ids["Ania"]: Decimal("0")}
        assert grid.total == Decimal("0")

    async def test_years_are_separate(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00", year=2025)
        assert (await svc.grid(YEAR)).total == Decimal("0")
        assert (await svc.grid(2025)).total == Decimal("200.00")

    async def test_an_empty_amount_deletes_the_cell(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert await _set(svc, ids, "Mama", "Urodziny", None) is None
        assert (await svc.grid(YEAR)).cells == []

    async def test_zero_is_a_cell_not_an_empty_one(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "0.00")
        grid = await svc.grid(YEAR)
        assert [c.amount for c in grid.cells] == [Decimal("0.00")]

    async def test_setting_a_cell_again_overwrites_it(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Inne"])
        first = await _set(svc, ids, "Mama", "Inne", "100.00", note="Dzień Matki")
        second = await _set(svc, ids, "Mama", "Inne", "120.00", note="Dzień Matki")
        assert first == second
        cell = _cell(await svc.grid(YEAR), ids, "Mama", "Inne")
        assert (cell.amount, cell.note) == (Decimal("120.00"), "Dzień Matki")

    async def test_a_missing_person_or_occasion_is_not_found(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        with pytest.raises(NotFoundError):
            await svc.set_cell(YEAR, 9999, ids["Urodziny"], GiftCellSet(amount=Decimal("1")))
        with pytest.raises(NotFoundError):
            await svc.set_cell(YEAR, ids["Mama"], 9999, GiftCellSet(amount=Decimal("1")))

    async def test_summary_is_one_years_total(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny", "Boże Narodzenie"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00")
        await _set(svc, ids, "Mama", "Boże Narodzenie", "150.00")
        await _set(svc, ids, "Mama", "Urodziny", "80.00", year=2025)
        assert (await svc.summary(YEAR)).yearly_total == Decimal("350.00")
        assert (await svc.summary(2027)).yearly_total == Decimal("0")

    async def test_summary_defaults_to_this_year(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00", year=datetime.date.today().year)
        summary = await svc.summary()
        assert (summary.year, summary.yearly_total) == (
            datetime.date.today().year,
            Decimal("200.00"),
        )


class TestLanes:
    async def test_default_occasions_are_created_once(self, svc: GiftService):
        names = ["Urodziny", "Imieniny", "Boże Narodzenie", "Wielkanoc", "Mikołajki", "Inne"]
        assert await svc.ensure_default_occasions(names) is True
        assert [o.name for o in await svc.occasions()] == names
        assert await svc.ensure_default_occasions(["Other"]) is False
        assert len(await svc.occasions()) == 6

    async def test_archived_defaults_do_not_come_back(self, svc: GiftService):
        await svc.ensure_default_occasions(["Urodziny"])
        [only] = await svc.occasions()
        await svc.archive_occasion(only.id)
        assert await svc.ensure_default_occasions(["Urodziny"]) is False

    async def test_adding_an_occasion_adds_an_empty_column(self, svc: GiftService):
        """Covers: KAL-GFT-005"""
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00")
        anniversary = await svc.add_occasion(GiftName(name="Rocznica ślubu"))
        grid = await svc.grid(YEAR)
        assert [o.name for o in grid.occasions] == ["Urodziny", "Rocznica ślubu"]
        assert grid.column_totals[anniversary.id] == Decimal("0")
        assert grid.total == Decimal("200.00")

    async def test_a_live_name_cannot_repeat(self, svc: GiftService):
        await _lanes(svc, ["Mama"], [])
        with pytest.raises(ConflictError):
            await svc.add_person(GiftName(name=" mama "))

    async def test_an_archived_name_can_be_reused(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], [])
        await svc.archive_person(ids["Mama"])
        again = await svc.add_person(GiftName(name="Mama"))
        assert again.id != ids["Mama"]

    async def test_a_blank_name_is_refused(self, svc: GiftService):
        with pytest.raises(ValidationError):
            await svc.add_person(GiftName(name="   "))

    async def test_rename(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama", "Tata"], [])
        await svc.rename_person(ids["Mama"], GiftName(name="Mamusia"))
        assert [p.name for p in await svc.people()] == ["Mamusia", "Tata"]
        with pytest.raises(ConflictError):
            await svc.rename_person(ids["Tata"], GiftName(name="Mamusia"))
        with pytest.raises(NotFoundError):
            await svc.rename_occasion(9999, GiftName(name="X"))

    async def test_move_swaps_neighbours_and_stops_at_the_ends(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama", "Tata", "Ania"], [])
        await svc.move_person(ids["Ania"], -1)
        assert [p.name for p in await svc.people()] == ["Mama", "Ania", "Tata"]
        await svc.move_person(ids["Mama"], -1)  # already first
        assert [p.name for p in await svc.people()] == ["Mama", "Ania", "Tata"]
        await svc.move_person(ids["Mama"], 1)
        assert [p.name for p in await svc.people()] == ["Ania", "Mama", "Tata"]

    async def test_move_occasion(self, svc: GiftService):
        ids = await _lanes(svc, [], ["Urodziny", "Wielkanoc"])
        await svc.move_occasion(ids["Wielkanoc"], -1)
        assert [o.name for o in await svc.occasions()] == ["Wielkanoc", "Urodziny"]

    async def test_archived_person_stays_only_in_years_with_cells(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama", "Babcia"], ["Urodziny"])
        await _set(svc, ids, "Babcia", "Urodziny", "100.00", year=2025)
        await svc.archive_person(ids["Babcia"])
        assert [p.name for p in (await svc.grid(2025)).people] == ["Mama", "Babcia"]
        assert [p.name for p in (await svc.grid(YEAR)).people] == ["Mama"]

    async def test_archived_occasion_stays_only_in_years_with_cells(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny", "Walentynki"])
        await _set(svc, ids, "Mama", "Walentynki", "50.00", year=2025)
        await svc.archive_occasion(ids["Walentynki"])
        assert [o.name for o in (await svc.grid(2025)).occasions] == ["Urodziny", "Walentynki"]
        assert [o.name for o in (await svc.grid(YEAR)).occasions] == ["Urodziny"]


class TestCopyYear:
    async def test_copy_brings_amounts_and_notes(self, svc: GiftService):
        """Covers: KAL-GFT-004"""
        ids = await _lanes(svc, ["Mama", "Tata"], ["Urodziny", "Boże Narodzenie", "Inne"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00", year=2026)
        await _set(svc, ids, "Mama", "Boże Narodzenie", "150.00", year=2026)
        await _set(svc, ids, "Tata", "Inne", "100.00", year=2026, note="Rocznica ślubu")

        assert (await svc.grid(2027)).previous_year_has_cells is True
        assert await svc.copy_year(2026, 2027) == 3
        grid = await svc.grid(2027)
        assert grid.total == Decimal("450.00")
        assert _cell(grid, ids, "Tata", "Inne").note == "Rocznica ślubu"

    async def test_copy_leaves_bought_behind(self, svc: GiftService, session: AsyncSession):
        """Covers: KAL-GFT-004"""
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00", year=2026)
        assert cell_id is not None
        await svc.link_transaction(cell_id, await _expense(session, "189.99"))

        await svc.copy_year(2026, 2027)
        assert [c.bought for c in (await svc.grid(2027)).cells] == [False]
        assert [c.bought for c in (await svc.grid(2026)).cells] == [True]

    async def test_copy_skips_archived_people(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama", "Babcia"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00", year=2026)
        await _set(svc, ids, "Babcia", "Urodziny", "100.00", year=2026)
        await svc.archive_person(ids["Babcia"])
        await svc.copy_year(2026, 2027)
        assert (await svc.grid(2027)).total == Decimal("200.00")

    async def test_copy_into_a_planned_year_conflicts(self, svc: GiftService):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        await _set(svc, ids, "Mama", "Urodziny", "200.00", year=2026)
        await _set(svc, ids, "Mama", "Urodziny", "10.00", year=2027)
        with pytest.raises(ConflictError):
            await svc.copy_year(2026, 2027)

    async def test_copy_from_an_empty_year_is_refused(self, svc: GiftService):
        await _lanes(svc, ["Mama"], ["Urodziny"])
        assert (await svc.grid(2027)).previous_year_has_cells is False
        with pytest.raises(ValidationError):
            await svc.copy_year(2026, 2027)


class TestBought:
    async def test_linking_a_transaction_marks_the_cell_bought(
        self, svc: GiftService, session: AsyncSession
    ):
        """Covers: KAL-GFT-003

        A gift planned at 200.00, linked to a 189.99 expense, is marked bought
        with that actual cost — the BDD literals.
        """
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        await svc.link_transaction(cell_id, await _expense(session, "189.99"))

        cell = _cell(await svc.grid(YEAR), ids, "Mama", "Urodziny")
        assert (cell.bought, cell.actual_cost, cell.amount) == (
            True,
            Decimal("189.99"),
            Decimal("200.00"),
        )

    async def test_actual_cost_sums_several_linked_transactions(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        await svc.link_transaction(cell_id, await _expense(session, "120.00"))
        await svc.link_transaction(cell_id, await _expense(session, "69.99"))
        assert _cell(await svc.grid(YEAR), ids, "Mama", "Urodziny").actual_cost == Decimal("189.99")

    async def test_mark_not_bought_unlinks(self, svc: GiftService, session: AsyncSession):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        await svc.link_transaction(cell_id, await _expense(session, "189.99"))
        await svc.mark_not_bought(cell_id)
        cell = _cell(await svc.grid(YEAR), ids, "Mama", "Urodziny")
        assert (cell.bought, cell.actual_cost) == (False, None)

    async def test_cannot_link_a_non_expense(self, svc: GiftService, session: AsyncSession):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        income_id = await _expense(session, "189.99", kind=TransactionType.INCOME)
        with pytest.raises(ValidationError):
            await svc.link_transaction(cell_id, income_id)

    async def test_link_missing_cell_or_transaction_raises(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        with pytest.raises(NotFoundError):
            await svc.link_transaction(9999, await _expense(session, "189.99"))
        with pytest.raises(NotFoundError):
            await svc.link_transaction(cell_id, 9999)
        with pytest.raises(NotFoundError):
            await svc.mark_not_bought(9999)

    async def test_relinking_to_another_cell_conflicts(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama", "Tata"], ["Urodziny"])
        first = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        second = await _set(svc, ids, "Tata", "Urodziny", "120.00")
        assert first is not None and second is not None
        tx_id = await _expense(session, "189.99")
        await svc.link_transaction(first, tx_id)
        with pytest.raises(ConflictError):
            await svc.link_transaction(second, tx_id)

    async def test_buyable_transactions_excludes_linked_ones(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        linked = await _expense(session, "189.99")
        free = await _expense(session, "50.00")
        await svc.link_transaction(cell_id, linked)
        ids_free = [tx.id for tx in await svc.buyable_transactions()]
        assert free in ids_free
        assert linked not in ids_free

    async def test_emptying_a_bought_cell_frees_its_expense(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        tx_id = await _expense(session, "189.99")
        await svc.link_transaction(cell_id, tx_id)
        await _set(svc, ids, "Mama", "Urodziny", None)
        session.expire_all()
        assert tx_id in [tx.id for tx in await svc.buyable_transactions()]

    async def test_deleting_the_linked_transaction_reverts_to_unbought(
        self, svc: GiftService, session: AsyncSession
    ):
        ids = await _lanes(svc, ["Mama"], ["Urodziny"])
        cell_id = await _set(svc, ids, "Mama", "Urodziny", "200.00")
        assert cell_id is not None
        tx_id = await _expense(session, "189.99")
        await svc.link_transaction(cell_id, tx_id)
        # Deleting the ledger row nulls the FK (ondelete SET NULL), so the
        # derived state falls back to unbought with no extra bookkeeping.
        await TransactionService(session).delete(tx_id)
        assert _cell(await svc.grid(YEAR), ids, "Mama", "Urodziny").bought is False
