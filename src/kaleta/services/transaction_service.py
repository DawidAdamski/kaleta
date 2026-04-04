from __future__ import annotations

import builtins
import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionSplit, TransactionType
from kaleta.schemas.transaction import TransactionCreate, TransactionUpdate


class TransactionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_stmt(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
    ) -> Any:
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
        if tag_ids:
            stmt = stmt.where(Transaction.tags.any(Tag.id.in_(tag_ids)))
        return stmt

    async def list(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[Transaction]:
        stmt = (
            self._base_stmt(
                account_ids, category_ids, date_from, date_to, tx_types, search, tag_ids
            )
            .options(
                selectinload(Transaction.account),
                selectinload(Transaction.category),
                selectinload(Transaction.payee),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
                selectinload(Transaction.tags),
            )
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def count(
        self,
        account_ids: builtins.list[int] | None = None,
        category_ids: builtins.list[int] | None = None,
        date_from: datetime.date | None = None,
        date_to: datetime.date | None = None,
        tx_types: builtins.list[TransactionType] | None = None,
        search: str | None = None,
        tag_ids: builtins.list[int] | None = None,
    ) -> int:
        stmt = self._base_stmt(
            account_ids, category_ids, date_from, date_to, tx_types, search, tag_ids
        )
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
                selectinload(Transaction.payee),
                selectinload(Transaction.splits).selectinload(TransactionSplit.category),
                selectinload(Transaction.tags),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _load_tags(self, tag_ids: builtins.list[int]) -> builtins.list[Tag]:
        if not tag_ids:
            return []
        result = await self.session.execute(select(Tag).where(Tag.id.in_(tag_ids)))
        return builtins.list(result.scalars())

    async def create(self, data: TransactionCreate) -> Transaction:
        transaction = Transaction(**data.model_dump(exclude={"splits", "tag_ids"}))
        self.session.add(transaction)
        await self.session.flush()
        for split_data in data.splits:
            split = TransactionSplit(transaction_id=transaction.id, **split_data.model_dump())
            self.session.add(split)
        if data.tag_ids:
            transaction.tags = await self._load_tags(data.tag_ids)
        await self.session.commit()
        # Re-fetch with eager-loaded relationships so the response serializer
        # never hits a lazy relationship outside of an async context.
        fetched = await self.get(transaction.id)
        if fetched is None:
            raise RuntimeError(f"Transaction id={transaction.id} not found after commit")
        return fetched

    async def create_bulk(self, creates: builtins.list[TransactionCreate]) -> int:
        """Insert many simple transactions in a single commit (no splits, no tags).

        Significantly faster than calling ``create()`` in a loop — intended for CSV
        import where transactions have no splits and no tags.
        Returns the number of inserted rows.
        """
        objects = [Transaction(**c.model_dump(exclude={"splits", "tag_ids"})) for c in creates]
        self.session.add_all(objects)
        await self.session.commit()
        return len(objects)

    async def create_transfer(
        self,
        outgoing: TransactionCreate,
        incoming: TransactionCreate,
    ) -> tuple[Transaction, Transaction]:
        """Create a paired internal transfer (two linked legs) atomically."""
        tx_out = Transaction(**outgoing.model_dump(exclude={"splits", "tag_ids"}))
        self.session.add(tx_out)
        await self.session.flush()  # get tx_out.id

        tx_in = Transaction(**incoming.model_dump(exclude={"splits", "tag_ids"}))
        tx_in.linked_transaction_id = tx_out.id
        self.session.add(tx_in)
        await self.session.flush()  # get tx_in.id

        tx_out.linked_transaction_id = tx_in.id
        await self.session.commit()
        fetched_out = await self.get(tx_out.id)
        fetched_in = await self.get(tx_in.id)
        if fetched_out is None or fetched_in is None:
            raise RuntimeError("Transfer legs not found after commit")
        return fetched_out, fetched_in

    async def update(self, transaction_id: int, data: TransactionUpdate) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        tag_ids = updates.pop("tag_ids", None)
        for field, value in updates.items():
            setattr(transaction, field, value)
        if tag_ids is not None:
            transaction.tags = await self._load_tags(tag_ids)
        await self.session.commit()
        return await self.get(transaction_id)

    async def delete(self, transaction_id: int) -> bool:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return False
        await self.session.delete(transaction)
        await self.session.commit()
        return True
