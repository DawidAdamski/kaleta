# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.gift import Gift
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.gift import (
    GiftCreate,
    GiftPersonGroup,
    GiftResponse,
    GiftsSummary,
    GiftUpdate,
)


class GiftService:
    """Planned gifts: per-person entries, the yearly total, and what was bought."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: GiftCreate) -> Gift:
        gift = Gift(person=payload.person, occasion=payload.occasion, amount=payload.amount)
        self.session.add(gift)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def get(self, gift_id: int) -> Gift | None:
        result = await self.session.execute(select(Gift).where(Gift.id == gift_id))
        return result.scalar_one_or_none()

    async def list(self) -> builtins.list[Gift]:
        result = await self.session.execute(select(Gift).order_by(Gift.id))
        return list(result.scalars().all())

    async def update(self, gift_id: int, payload: GiftUpdate) -> Gift:
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(gift, key, value)
        await self.session.commit()
        await self.session.refresh(gift)
        return gift

    async def delete(self, gift_id: int) -> None:
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        await self.session.delete(gift)
        await self.session.commit()

    # ── Bought / actual cost (``KAL-GFT-003``) ─────────────────────────────

    async def _actuals(self, gift_ids: builtins.list[int]) -> dict[int, Decimal]:
        """Sum of the linked transactions' amounts, per gift — bought is ``in`` this.

        ``gift_id`` and ``amount`` are plain columns, so this groups in SQL.
        """
        if not gift_ids:
            return {}
        rows = await self.session.execute(
            select(Transaction.gift_id, func.sum(Transaction.amount))
            .where(Transaction.gift_id.in_(gift_ids))
            .group_by(Transaction.gift_id)
        )
        return {gid: total for gid, total in rows.all() if gid is not None}

    def _to_response(self, gift: Gift, actuals: dict[int, Decimal]) -> GiftResponse:
        cost = actuals.get(gift.id)
        return GiftResponse(
            id=gift.id,
            person=gift.person,
            occasion=gift.occasion,
            amount=gift.amount,
            bought=cost is not None,
            actual_cost=cost,
        )

    async def get_response(self, gift_id: int) -> GiftResponse | None:
        """One gift with its bought state, for callers that need a single row."""
        gift = await self.get(gift_id)
        if gift is None:
            return None
        return self._to_response(gift, await self._actuals([gift_id]))

    async def link_transaction(self, gift_id: int, transaction_id: int) -> None:
        """Mark a gift bought by pointing a ledger expense at it."""
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        tx = await self.session.get(Transaction, transaction_id)
        if tx is None:
            raise NotFoundError(f"Transaction {transaction_id} not found")
        if tx.type is not TransactionType.EXPENSE:
            raise ValidationError("Only an expense can pay for a gift.")
        if tx.gift_id is not None and tx.gift_id != gift_id:
            raise ConflictError("That transaction already pays for another gift.")
        tx.gift_id = gift_id
        await self.session.commit()

    async def mark_not_bought(self, gift_id: int) -> None:
        """Undo: unlink every transaction from the gift (it is planned again)."""
        gift = await self.get(gift_id)
        if gift is None:
            raise NotFoundError(f"Gift {gift_id} not found")
        await self.session.execute(
            update(Transaction).where(Transaction.gift_id == gift_id).values(gift_id=None)
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

    async def summary(self) -> GiftsSummary:
        """The list grouped by person (names are encrypted, so group in Python).

        Groups are ordered by person (case-insensitive); gifts within a group
        keep insertion order (by id). The yearly total is the plain sum of every
        gift's amount. Each gift carries whether it was bought and its actual
        cost, from the linked transactions.
        """
        gifts = await self.list()
        actuals = await self._actuals([gift.id for gift in gifts])

        by_person: dict[str, list[GiftResponse]] = {}
        for gift in gifts:
            by_person.setdefault(gift.person, []).append(self._to_response(gift, actuals))

        groups = [
            GiftPersonGroup(
                person=person,
                gifts=entries,
                subtotal=sum((g.amount for g in entries), Decimal("0")),
            )
            for person, entries in sorted(by_person.items(), key=lambda kv: kv[0].casefold())
        ]
        yearly_total = sum((group.subtotal for group in groups), Decimal("0"))
        return GiftsSummary(groups=groups, yearly_total=yearly_total)
