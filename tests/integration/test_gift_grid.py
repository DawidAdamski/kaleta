# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gift grid on a family schema built by the real migrations.

Covers: KAL-GFT-001, KAL-GFT-004, KAL-GFT-005

The suite family's schema is provisioned through Alembic (``tests/suite_family``),
so these tests also pin the ``gift_grid`` migration to the models: the
columns, the one-cell-per-slot constraint and the repointed
``transactions.gift_id`` foreign key are read back from the database.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from kaleta.models.gift import GiftCell, GiftOccasion, GiftPerson
from kaleta.schemas.gift import GiftCellSet, GiftName
from kaleta.services import GiftService
from tests.conftest import SUITE_FAMILY


async def _inspect(conn: AsyncConnection, fn: Any) -> Any:
    return await conn.run_sync(lambda sync: fn(inspect(sync)))


async def test_the_migration_builds_what_the_models_declare(db_engine: AsyncConnection) -> None:
    schema = SUITE_FAMILY.schema
    for model in (GiftPerson, GiftOccasion, GiftCell):
        table = model.__table__
        columns = await _inspect(db_engine, lambda i, n=table.name: i.get_columns(n, schema=schema))
        assert {c["name"]: c["nullable"] for c in columns} == {
            c.name: c.nullable for c in table.columns
        }, table.name

    uniques = await _inspect(
        db_engine, lambda i: i.get_unique_constraints("gift_cells", schema=schema)
    )
    assert [(u["name"], u["column_names"]) for u in uniques] == [
        ("uq_gift_cells_slot", ["year", "person_id", "occasion_id"])
    ]
    tables = await _inspect(db_engine, lambda i: i.get_table_names(schema=schema))
    assert "gifts" not in tables

    fks = await _inspect(db_engine, lambda i: i.get_foreign_keys("transactions", schema=schema))
    gift_fk = next(fk for fk in fks if fk["constrained_columns"] == ["gift_id"])
    assert (gift_fk["referred_table"], gift_fk["options"].get("ondelete")) == (
        "gift_cells",
        "SET NULL",
    )


async def _grid_2026(svc: GiftService) -> dict[str, int]:
    """KAL-GFT-001's literals: Mama 200 + 150, Tata 100."""
    ids: dict[str, int] = {}
    for name in ("Mama", "Tata"):
        ids[name] = (await svc.add_person(GiftName(name=name))).id
    for name in ("Urodziny", "Boże Narodzenie"):
        ids[name] = (await svc.add_occasion(GiftName(name=name))).id
    for person, occasion, amount in (
        ("Mama", "Urodziny", "200.00"),
        ("Mama", "Boże Narodzenie", "150.00"),
        ("Tata", "Boże Narodzenie", "100.00"),
    ):
        await svc.set_cell(2026, ids[person], ids[occasion], GiftCellSet(amount=Decimal(amount)))
    return ids


async def test_the_grid_adds_up(session: AsyncSession) -> None:
    """Covers: KAL-GFT-001"""
    svc = GiftService(session)
    ids = await _grid_2026(svc)
    grid = await svc.grid(2026)
    assert grid.row_totals == {ids["Mama"]: Decimal("350.00"), ids["Tata"]: Decimal("100.00")}
    assert grid.column_totals[ids["Boże Narodzenie"]] == Decimal("250.00")
    assert grid.total == Decimal("450.00")


async def test_a_new_year_starts_as_a_copy(session: AsyncSession) -> None:
    """Covers: KAL-GFT-004"""
    svc = GiftService(session)
    await _grid_2026(svc)
    assert (await svc.grid(2027)).total == Decimal("0")
    await svc.copy_year(2026, 2027)
    assert (await svc.grid(2027)).total == Decimal("450.00")


async def test_a_new_occasion_is_an_empty_column(session: AsyncSession) -> None:
    """Covers: KAL-GFT-005"""
    svc = GiftService(session)
    await _grid_2026(svc)
    anniversary = await svc.add_occasion(GiftName(name="Rocznica ślubu"))
    grid = await svc.grid(2026)
    assert grid.occasions[-1].name == "Rocznica ślubu"
    assert grid.column_totals[anniversary.id] == Decimal("0")
    assert grid.total == Decimal("450.00")
