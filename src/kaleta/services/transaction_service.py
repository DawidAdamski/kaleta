from __future__ import annotations

import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.transaction import Transaction, TransactionSplit, TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_stmt(
        self,
        account_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: list[TransactionType] | None = None,
        search: str | None = None,
    ):  # type: ignore[return]
        stmt = select(Transaction)
        if account_ids:
            stmt = stmt.where(Transaction.account_id.in_(account_ids))
        if category_ids:
            stmt = stmt.where(Transaction.category_id.in_(category_ids))
        if date_from is not None:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Transaction.date <= date_to)
        if tx_types:
            stmt = stmt.where(Transaction.type.in_(tx_types))
        if search:
            stmt = stmt.where(Transaction.description.ilike(f"%{search}%"))
        return stmt

    async def list(
        self,
        account_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: list[TransactionType] | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transaction]:
        stmt = (
            self._base_stmt(account_ids, category_ids, date_from, date_to, tx_types, search)
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        account_ids: list[int] | None = None,
        category_ids: list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: list[TransactionType] | None = None,
        search: str | None = None,
    ) -> int:
        stmt = self._base_stmt(account_ids, category_ids, date_from, date_to, tx_types, search)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await self.session.execute(count_stmt)
        return result.scalar_one()

    async def get(self, transaction_id: int) -> Transaction | None:
        stmt = (
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create(self, data: TransactionCreate) -> Transaction:
        transaction = Transaction(**data.model_dump(exclude={"splits"}))
        self.session.add(transaction)
        await self.session.flush()
        for split_data in data.splits:
            split = TransactionSplit(transaction_id=transaction.id, **split_data.model_dump())
            self.session.add(split)
        await self.session.commit()
        # Re-fetch with eager-loaded relationships so the response serializer
        # never hits a lazy relationship outside of an async context.
        fetched = await self.get(transaction.id)
        assert fetched is not None
        return fetched

    async def create_transfer(
        self,
        outgoing: TransactionCreate,
        incoming: TransactionCreate,
    ) -> tuple[Transaction, Transaction]:
        """Create a paired internal transfer (two linked legs) atomically."""
        tx_out = Transaction(**outgoing.model_dump(exclude={"splits"}))
        self.session.add(tx_out)
        await self.session.flush()  # get tx_out.id

        tx_in = Transaction(**incoming.model_dump(exclude={"splits"}))
        tx_in.linked_transaction_id = tx_out.id
        self.session.add(tx_in)
        await self.session.flush()  # get tx_in.id

        tx_out.linked_transaction_id = tx_in.id
        await self.session.commit()
        fetched_out = await self.get(tx_out.id)
        fetched_in = await self.get(tx_in.id)
        assert fetched_out is not None and fetched_in is not None
        return fetched_out, fetched_in

    async def update(self, transaction_id: int, data: TransactionUpdate) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(transaction, field, value)
        await self.session.commit()
        return await self.get(transaction_id)

    async def delete(self, transaction_id: int) -> bool:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return False
        await self.session.delete(transaction)
        await self.session.commit()
        return True
