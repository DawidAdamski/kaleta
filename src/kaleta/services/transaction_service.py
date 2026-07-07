# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins
import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import KaletaError, ValidationError
from kaleta.models.tag import Tag
from kaleta.models.transaction import Transaction, TransactionSplit, TransactionType
from kaleta.schemas.transaction import (
    TransactionCreate,
    TransactionSplitCreate,
    TransactionUpdate,
)


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
        # Load tags up-front so we can pass them to the constructor — assigning
        # to ``.tags`` post-insert would trigger a lazy-load of the (empty)
        # collection in sync context and raise MissingGreenlet.
        tags = await self._load_tags(data.tag_ids) if data.tag_ids else []
        transaction = Transaction(
            **data.model_dump(exclude={"splits", "tag_ids"}),
            tags=tags,
        )
        self.session.add(transaction)
        await self.session.flush()
        for split_data in data.splits:
            split = TransactionSplit(transaction_id=transaction.id, **split_data.model_dump())
            self.session.add(split)
        await self.session.commit()
        # Re-fetch with eager-loaded relationships so the response serializer
        # never hits a lazy relationship outside of an async context.
        fetched = await self.get(transaction.id)
        if fetched is None:
            raise KaletaError(f"Transaction id={transaction.id} not found after commit")
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
            raise KaletaError("Transfer legs not found after commit")
        return fetched_out, fetched_in

    @staticmethod
    def _validate_split_sum(amount: Decimal, splits: builtins.list[TransactionSplitCreate]) -> None:
        if not splits:
            raise ValidationError("Split transactions must have at least one split.")
        split_total = sum((s.amount for s in splits), start=Decimal("0"))
        if split_total != amount:
            remaining = amount - split_total
            raise ValidationError(
                f"Split amounts must sum to {amount}; {remaining:+.2f} remaining."
            )

    async def update(self, transaction_id: int, data: TransactionUpdate) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        fields_set = data.model_fields_set
        updates = data.model_dump(exclude_unset=True, exclude={"splits", "is_split", "tag_ids"})
        splits = data.splits if "splits" in fields_set else None
        is_split = data.is_split if "is_split" in fields_set else None
        tag_ids = data.tag_ids if "tag_ids" in fields_set else None

        if (
            transaction.is_split
            and "amount" in updates
            and updates["amount"] != transaction.amount
            and splits is None
        ):
            raise ValidationError(
                "Cannot change amount on a split transaction without updating splits."
            )

        effective_type = (
            data.type if "type" in fields_set and data.type is not None else transaction.type
        )
        if (
            is_split is False
            and transaction.is_split
            and effective_type in (TransactionType.INCOME, TransactionType.EXPENSE)
            and ("category_id" not in fields_set or data.category_id is None)
        ):
            raise ValidationError(
                f"{effective_type.value.capitalize()} transactions require a category."
            )

        for field, value in updates.items():
            setattr(transaction, field, value)

        if is_split is not None:
            transaction.is_split = is_split
            if is_split:
                transaction.category_id = None
            elif transaction.splits:
                transaction.splits.clear()

        if splits is not None:
            self._validate_split_sum(transaction.amount, splits)
            transaction.is_split = True
            transaction.category_id = None
            transaction.splits.clear()
            for split_data in splits:
                transaction.splits.append(TransactionSplit(**split_data.model_dump()))

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

    @staticmethod
    def category_display_label(transaction: Transaction) -> str:
        if transaction.is_split and transaction.splits:
            names = [s.category.name for s in transaction.splits if s.category]
            return f"(Split: {', '.join(names)})" if names else "(Split)"
        return transaction.category.name if transaction.category else "—"

    @staticmethod
    def group_separator_label(
        tx_date: datetime.date,
        prev_date: datetime.date | None,
        grouping: str,
    ) -> str:
        if grouping == "none":
            return ""
        if grouping == "week":
            year, week, _ = tx_date.isocalendar()
            label = f"W{week:02d} {year}"
            if prev_date is None:
                return label
            py, pw, _ = prev_date.isocalendar()
            return label if (year, week) != (py, pw) else ""
        label = tx_date.strftime("%B %Y")
        if prev_date is None:
            return label
        return label if (tx_date.year, tx_date.month) != (prev_date.year, prev_date.month) else ""

    @staticmethod
    def format_signed_amount(amount: Decimal, tx_type: TransactionType) -> str:
        if tx_type == TransactionType.INCOME:
            return f"+{abs(amount):,.2f}"
        return f"-{abs(amount):,.2f}"

    @staticmethod
    def split_balance(
        main_amount: Decimal, split_amounts: builtins.list[Decimal]
    ) -> tuple[bool, Decimal]:
        total_split = sum(split_amounts, start=Decimal("0"))
        remaining = main_amount - total_split
        return remaining == Decimal("0"), remaining

    @staticmethod
    def build_table_row(
        transaction: Transaction,
        prev_transaction: Transaction | None,
        grouping: str,
    ) -> dict[str, Any]:
        prev_date = prev_transaction.date if prev_transaction else None
        return {
            "id": transaction.id,
            "date": str(transaction.date),
            "account": transaction.account.name if transaction.account else "—",
            "description": (transaction.description or "—")[:55],
            "category": TransactionService.category_display_label(transaction),
            "type": transaction.type.value,
            "amount": TransactionService.format_signed_amount(transaction.amount, transaction.type),
            "tags": "",
            "tags_data": [
                {
                    "id": tg.id,
                    "name": tg.name,
                    "color": tg.color or "#9E9E9E",
                    "icon": tg.icon or "label",
                }
                for tg in transaction.tags
            ],
            "sep_label": TransactionService.group_separator_label(
                transaction.date, prev_date, grouping
            ),
        }

    @staticmethod
    def build_table_rows(
        transactions: builtins.list[Transaction],
        grouping: str,
    ) -> builtins.list[dict[str, Any]]:
        rows: builtins.list[dict[str, Any]] = []
        for i, tx in enumerate(transactions):
            prev_tx = transactions[i - 1] if i > 0 else None
            rows.append(TransactionService.build_table_row(tx, prev_tx, grouping))
        return rows
