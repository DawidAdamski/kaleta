from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction
from kaleta.schemas.payee import PayeeCreate, PayeeUpdate


class PayeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Payee]:
        result = await self.session.execute(select(Payee).order_by(Payee.name))
        return list(result.scalars().all())

    async def list_with_counts(self) -> list[tuple[Payee, int]]:
        """Return (payee, tx_count) tuples ordered by name."""
        stmt = (
            select(Payee, func.count(Transaction.id).label("tx_count"))
            .outerjoin(Transaction, Transaction.payee_id == Payee.id)
            .group_by(Payee.id)
            .order_by(Payee.name)
        )
        result = await self.session.execute(stmt)
        return [(row.Payee, row.tx_count) for row in result]

    async def get(self, payee_id: int) -> Payee | None:
        result = await self.session.execute(
            select(Payee).where(Payee.id == payee_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: PayeeCreate) -> Payee:
        payee = Payee(**data.model_dump())
        self.session.add(payee)
        await self.session.commit()
        await self.session.refresh(payee)
        return payee

    async def update(self, payee_id: int, data: PayeeUpdate) -> Payee | None:
        payee = await self.get(payee_id)
        if payee is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(payee, field, value)
        await self.session.commit()
        await self.session.refresh(payee)
        return payee

    async def delete(self, payee_id: int) -> bool:
        payee = await self.get(payee_id)
        if payee is None:
            return False
        await self.session.delete(payee)
        await self.session.commit()
        return True

    async def merge(self, keep_id: int, merge_ids: list[int]) -> int:
        """Reassign all transactions from *merge_ids* to *keep_id*, then delete merged payees.

        Returns the number of deleted payees.
        """
        if not merge_ids:
            return 0
        await self.session.execute(
            update(Transaction)
            .where(Transaction.payee_id.in_(merge_ids))
            .values(payee_id=keep_id)
        )
        deleted = 0
        for pid in merge_ids:
            payee = await self.get(pid)
            if payee is not None:
                await self.session.delete(payee)
                deleted += 1
        await self.session.commit()
        return deleted

    async def find_or_create(self, name: str) -> Payee:
        """Exact-match lookup; creates a new payee if not found.

        Does NOT commit — the caller owns the transaction.
        Uses flush() to make the new ID available within the current session.

        Note: SQLite's lower() does not handle non-ASCII characters (e.g. Polish
        ą/ę/ó/ł), so case-insensitive comparison via func.lower() would fail to
        find rows whose names contain such characters.  Exact-match is correct
        here because mBank payee names arrive as ALL-CAPS and are stored as-is.
        """
        name_clean = name.strip()
        result = await self.session.execute(
            select(Payee).where(Payee.name == name_clean)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        payee = Payee(name=name_clean)
        self.session.add(payee)
        await self.session.flush()
        return payee
