# SPDX-License-Identifier: AGPL-3.0-or-later
"""The gift grid: people by occasions, one amount per cell, one grid per year."""

from __future__ import annotations

import builtins
import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.gift import GiftCell, GiftOccasion, GiftPerson
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.gift import (
    GiftCellResponse,
    GiftCellSet,
    GiftGrid,
    GiftLaneResponse,
    GiftName,
    GiftsSummary,
)

_Lane = TypeVar("_Lane", GiftPerson, GiftOccasion)

_ZERO = Decimal("0")


class GiftService:
    """People (rows), occasions (columns) and the yearly cells between them.

    Names and notes are encrypted, so ordering and duplicate checks happen in
    Python. Every write commits on its own: the page saves one cell at a time.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── People and occasions ───────────────────────────────────────────────

    async def _lanes(self, model: type[_Lane]) -> builtins.list[_Lane]:
        result = await self.session.execute(select(model).order_by(model.position, model.id))
        return list(result.scalars().all())

    async def people(self) -> builtins.list[GiftPerson]:
        return await self._lanes(GiftPerson)

    async def occasions(self) -> builtins.list[GiftOccasion]:
        return await self._lanes(GiftOccasion)

    async def _get_lane(self, model: type[_Lane], lane_id: int) -> _Lane:
        lane = await self.session.get(model, lane_id)
        if lane is None:
            kind = "person" if model is GiftPerson else "occasion"
            raise NotFoundError(
                f"Gift {kind} {lane_id} not found",
                message_key=f"errors.gift.{kind}_not_found",
                params={"id": lane_id},
            )
        return lane

    async def _check_name_free(
        self, model: type[_Lane], name: str, *, except_id: int | None = None
    ) -> None:
        """Two live rows (or columns) with one name would be indistinguishable."""
        wanted = name.casefold()
        for lane in await self._lanes(model):
            if lane.id != except_id and not lane.archived and lane.name.casefold() == wanted:
                raise ConflictError(
                    f"{name!r} is already in the grid.",
                    message_key="errors.gift.name_taken",
                    params={"name": name},
                )

    async def _add_lane(self, model: type[_Lane], payload: GiftName) -> _Lane:
        name = payload.name.strip()
        if not name:
            raise ValidationError("A name is required.", message_key="errors.gift.name_required")
        await self._check_name_free(model, name)
        lanes = await self._lanes(model)
        lane = model(name=name, position=max((x.position for x in lanes), default=-1) + 1)
        self.session.add(lane)
        await self.session.commit()
        await self.session.refresh(lane)
        return lane

    async def add_person(self, payload: GiftName) -> GiftPerson:
        return await self._add_lane(GiftPerson, payload)

    async def add_occasion(self, payload: GiftName) -> GiftOccasion:
        return await self._add_lane(GiftOccasion, payload)

    async def _rename_lane(self, model: type[_Lane], lane_id: int, payload: GiftName) -> _Lane:
        lane = await self._get_lane(model, lane_id)
        name = payload.name.strip()
        if not name:
            raise ValidationError("A name is required.", message_key="errors.gift.name_required")
        await self._check_name_free(model, name, except_id=lane_id)
        lane.name = name
        await self.session.commit()
        return lane

    async def rename_person(self, person_id: int, payload: GiftName) -> GiftPerson:
        return await self._rename_lane(GiftPerson, person_id, payload)

    async def rename_occasion(self, occasion_id: int, payload: GiftName) -> GiftOccasion:
        return await self._rename_lane(GiftOccasion, occasion_id, payload)

    async def _move_lane(self, model: type[_Lane], lane_id: int, step: int) -> None:
        """Swap with the live neighbour ``step`` places away (−1 up/left, +1 down/right)."""
        await self._get_lane(model, lane_id)
        live = [lane for lane in await self._lanes(model) if not lane.archived]
        # Renumber first: positions may have gaps or ties after archiving.
        for position, lane in enumerate(live):
            lane.position = position
        ids = [lane.id for lane in live]
        if lane_id in ids and 0 <= ids.index(lane_id) + step < len(live):
            here, there = live[ids.index(lane_id)], live[ids.index(lane_id) + step]
            here.position, there.position = there.position, here.position
        await self.session.commit()

    async def move_person(self, person_id: int, step: int) -> None:
        await self._move_lane(GiftPerson, person_id, step)

    async def move_occasion(self, occasion_id: int, step: int) -> None:
        await self._move_lane(GiftOccasion, occasion_id, step)

    async def _archive_lane(self, model: type[_Lane], lane_id: int) -> None:
        lane = await self._get_lane(model, lane_id)
        lane.archived = True
        await self.session.commit()

    async def archive_person(self, person_id: int) -> None:
        """Take a person off the grid; their past years' cells stay."""
        await self._archive_lane(GiftPerson, person_id)

    async def archive_occasion(self, occasion_id: int) -> None:
        """Take an occasion off the grid; its past years' cells stay."""
        await self._archive_lane(GiftOccasion, occasion_id)

    async def ensure_default_occasions(self, names: Sequence[str]) -> bool:
        """Give a user who has never had an occasion the default columns.

        ``names`` come from the caller (the page, in the user's language).
        Archived occasions count: a user who removed every default does not
        get them back. Returns whether anything was created.
        """
        existing = await self.session.scalar(select(func.count()).select_from(GiftOccasion))
        if existing:
            return False
        self.session.add_all(
            GiftOccasion(name=name, position=index) for index, name in enumerate(names)
        )
        await self.session.commit()
        return True

    # ── Cells ──────────────────────────────────────────────────────────────

    async def _cell_at(self, year: int, person_id: int, occasion_id: int) -> GiftCell | None:
        result = await self.session.execute(
            select(GiftCell).where(
                GiftCell.year == year,
                GiftCell.person_id == person_id,
                GiftCell.occasion_id == occasion_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_cell(
        self, year: int, person_id: int, occasion_id: int, payload: GiftCellSet
    ) -> GiftCell | None:
        """Write one cell; an empty amount deletes it (and unlinks its expenses)."""
        await self._get_lane(GiftPerson, person_id)
        await self._get_lane(GiftOccasion, occasion_id)
        cell = await self._cell_at(year, person_id, occasion_id)
        if payload.amount is None:
            if cell is not None:
                await self.session.delete(cell)
                await self.session.commit()
            return None
        note = (payload.note or "").strip() or None
        if cell is None:
            cell = GiftCell(
                year=year,
                person_id=person_id,
                occasion_id=occasion_id,
                amount=payload.amount,
                note=note,
            )
            self.session.add(cell)
        else:
            cell.amount = payload.amount
            cell.note = note
        await self.session.commit()
        await self.session.refresh(cell)
        return cell

    async def _cells(self, year: int) -> builtins.list[GiftCell]:
        result = await self.session.execute(
            select(GiftCell).where(GiftCell.year == year).order_by(GiftCell.id)
        )
        return list(result.scalars().all())

    async def _year_has_cells(self, year: int) -> bool:
        count = await self.session.scalar(
            select(func.count()).select_from(GiftCell).where(GiftCell.year == year)
        )
        return bool(count)

    async def copy_year(self, from_year: int, to_year: int) -> int:
        """Start ``to_year`` as a copy of ``from_year``'s amounts and notes.

        Nothing is marked bought in the copy: a link belongs to the expense
        that paid, which happened in the source year. Archived people and
        occasions are left behind. Refuses a target that already has cells.
        """
        if await self._year_has_cells(to_year):
            raise ConflictError(
                f"{to_year} already has gifts.",
                message_key="errors.gift.year_not_empty",
                params={"year": to_year},
            )
        live_people = {p.id for p in await self.people() if not p.archived}
        live_occasions = {o.id for o in await self.occasions() if not o.archived}
        source = [
            cell
            for cell in await self._cells(from_year)
            if cell.person_id in live_people and cell.occasion_id in live_occasions
        ]
        if not source:
            raise ValidationError(
                f"{from_year} has no gifts to copy.",
                message_key="errors.gift.nothing_to_copy",
                params={"year": from_year},
            )
        self.session.add_all(
            GiftCell(
                year=to_year,
                person_id=cell.person_id,
                occasion_id=cell.occasion_id,
                amount=cell.amount,
                note=cell.note,
            )
            for cell in source
        )
        await self.session.commit()
        return len(source)

    # ── The grid ───────────────────────────────────────────────────────────

    async def grid(self, year: int) -> GiftGrid:
        """One year: live rows and columns, plus archived ones that hold its cells."""
        cells = await self._cells(year)
        used_people = {cell.person_id for cell in cells}
        used_occasions = {cell.occasion_id for cell in cells}
        people = [p for p in await self.people() if not p.archived or p.id in used_people]
        occasions = [o for o in await self.occasions() if not o.archived or o.id in used_occasions]
        actuals = await self._actuals([cell.id for cell in cells])

        row_totals = {p.id: _ZERO for p in people}
        column_totals = {o.id: _ZERO for o in occasions}
        for cell in cells:
            row_totals[cell.person_id] += cell.amount
            column_totals[cell.occasion_id] += cell.amount

        return GiftGrid(
            year=year,
            people=[GiftLaneResponse.model_validate(p) for p in people],
            occasions=[GiftLaneResponse.model_validate(o) for o in occasions],
            cells=[self._to_response(cell, actuals) for cell in cells],
            row_totals=row_totals,
            column_totals=column_totals,
            total=sum((cell.amount for cell in cells), _ZERO),
            previous_year_has_cells=await self._year_has_cells(year - 1),
        )

    async def summary(self, year: int | None = None) -> GiftsSummary:
        """One year's gift total (this year by default), for the irregular fund."""
        year = year if year is not None else datetime.date.today().year
        total = await self.session.scalar(
            select(func.coalesce(func.sum(GiftCell.amount), 0)).where(GiftCell.year == year)
        )
        return GiftsSummary(year=year, yearly_total=Decimal(total or 0))

    # ── Bought / actual cost (``KAL-GFT-003``) ─────────────────────────────

    async def _actuals(self, cell_ids: builtins.list[int]) -> dict[int, Decimal]:
        """Sum of the linked expenses per cell — a cell is bought if it is in this."""
        if not cell_ids:
            return {}
        rows = await self.session.execute(
            select(Transaction.gift_id, func.sum(Transaction.amount))
            .where(Transaction.gift_id.in_(cell_ids))
            .group_by(Transaction.gift_id)
        )
        return {gid: total for gid, total in rows.all() if gid is not None}

    @staticmethod
    def _to_response(cell: GiftCell, actuals: dict[int, Decimal]) -> GiftCellResponse:
        cost = actuals.get(cell.id)
        return GiftCellResponse(
            id=cell.id,
            person_id=cell.person_id,
            occasion_id=cell.occasion_id,
            amount=cell.amount,
            note=cell.note,
            bought=cost is not None,
            actual_cost=cost,
        )

    async def _get_cell(self, cell_id: int) -> GiftCell:
        cell = await self.session.get(GiftCell, cell_id)
        if cell is None:
            raise NotFoundError(
                f"Gift {cell_id} not found",
                message_key="errors.gift.not_found",
                params={"gift_id": cell_id},
            )
        return cell

    async def link_transaction(self, cell_id: int, transaction_id: int) -> None:
        """Mark a cell bought by pointing a ledger expense at it."""
        await self._get_cell(cell_id)
        tx = await self.session.get(Transaction, transaction_id)
        if tx is None:
            raise NotFoundError(
                f"Transaction {transaction_id} not found",
                message_key="errors.gift.transaction_not_found",
                params={"transaction_id": transaction_id},
            )
        if tx.type is not TransactionType.EXPENSE:
            raise ValidationError(
                "Only an expense can pay for a gift.",
                message_key="errors.gift.only_expense_pays",
            )
        if tx.gift_id is not None and tx.gift_id != cell_id:
            raise ConflictError(
                "That transaction already pays for another gift.",
                message_key="errors.gift.transaction_pays_another",
            )
        tx.gift_id = cell_id
        await self.session.commit()

    async def mark_not_bought(self, cell_id: int) -> None:
        """Undo: unlink every expense from the cell (it is planned again)."""
        await self._get_cell(cell_id)
        await self.session.execute(
            update(Transaction).where(Transaction.gift_id == cell_id).values(gift_id=None)
        )
        await self.session.commit()

    async def buyable_transactions(self, limit: int = 50) -> builtins.list[Transaction]:
        """Recent expenses not yet linked to any gift — the "mark bought" picker.

        The unlinked filter is in the query, not applied after the fact, so an
        already-bought expense never uses up a slot and hides an older free one.
        """
        result = await self.session.execute(
            select(Transaction)
            .where(
                Transaction.type == TransactionType.EXPENSE,
                Transaction.gift_id.is_(None),
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
