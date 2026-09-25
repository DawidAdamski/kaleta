# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.payee import PayeeCreate, PayeeLastUsed, PayeeUpdate

#: Mirrors ``Payee.name``'s column width and the schemas' ``max_length``.
PAYEE_NAME_MAX_LENGTH = 200


class PayeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> builtins.list[Payee]:
        result = await self.session.execute(select(Payee).order_by(Payee.name))
        return builtins.list(result.scalars().all())

    async def list_with_counts(self) -> builtins.list[tuple[Payee, int]]:
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
        result = await self.session.execute(select(Payee).where(Payee.id == payee_id))
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

    async def merge(
        self, keep_id: int, merge_ids: builtins.list[int], *, new_name: str | None = None
    ) -> int:
        """Reassign all transactions from *merge_ids* to *keep_id*, then delete merged payees.

        ``new_name`` renames the kept payee in the same commit; blank keeps its
        name. Returns the number of deleted payees.
        """
        if not merge_ids:
            return 0
        name = (new_name or "").strip()
        keeper: Payee | None = None
        if name:
            keeper = await self.check_merge_name(name, keeper_id=keep_id, merged_ids=merge_ids)
        await self.session.execute(
            update(Transaction).where(Transaction.payee_id.in_(merge_ids)).values(payee_id=keep_id)
        )
        deleted = 0
        for pid in merge_ids:
            payee = await self.get(pid)
            if payee is not None:
                await self.session.delete(payee)
                deleted += 1
        if keeper is not None and keeper.name != name:
            # Flush the deletes first: the unit of work runs updates before
            # deletes, so taking a merged payee's name would trip UNIQUE.
            await self.session.flush()
            keeper.name = name
        await self.session.commit()
        return deleted

    async def check_merge_name(
        self, name: str, *, keeper_id: int, merged_ids: builtins.list[int]
    ) -> Payee:
        """Validate a merge's new name before anything is written; return the keeper.

        The name may be one a merged payee holds — that payee is about to go.
        A payee outside the merge holding it is a conflict (names are unique).
        """
        if len(name) > PAYEE_NAME_MAX_LENGTH:
            raise ValidationError(f"Payee name is longer than {PAYEE_NAME_MAX_LENGTH} characters")
        keeper = await self.get(keeper_id)
        if keeper is None:
            raise NotFoundError("Payee not found")
        clash = await self.session.execute(
            select(Payee.id).where(Payee.name == name, Payee.id.not_in([keeper_id, *merged_ids]))
        )
        if clash.first() is not None:
            raise ConflictError(f"A payee named '{name}' already exists")
        return keeper

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
        result = await self.session.execute(select(Payee).where(Payee.name == name_clean))
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        payee = Payee(name=name_clean)
        self.session.add(payee)
        await self.session.flush()
        return payee

    async def match_or_create_by_name(self, name: str) -> Payee:
        """Case-insensitive name lookup; creates the payee when nothing matches.

        Does NOT commit — the caller owns the transaction; ``flush()`` makes the
        new ID available within the current session.

        Distinct from :meth:`find_or_create`, which matches case-sensitively
        because mBank exports arrive ALL-CAPS and must stay one payee per exact
        spelling. Here the name is typed by a human, so "biedronka" has to find
        "Biedronka". SQLite's ``lower()`` only folds ASCII, so the fold is done
        in Python — otherwise Polish names (Żabka, Empik Ł.) would never match.

        The fold only runs when the indexed exact match misses, and then scans
        the payee table. That is the right trade at this scale (a personal ledger
        holds tens to low hundreds of payees); a generated ``lower(name)`` column
        would be the fix if it ever stops being.
        """
        name_clean = name.strip()
        result = await self.session.execute(select(Payee).where(Payee.name == name_clean))
        exact = result.scalar_one_or_none()
        if exact is not None:
            return exact

        folded = name_clean.casefold()
        candidates = await self.session.execute(select(Payee).order_by(Payee.id))
        for payee in candidates.scalars():
            if payee.name.casefold() == folded:
                return payee

        payee = Payee(name=name_clean)
        self.session.add(payee)
        await self.session.flush()
        return payee

    async def last_used_for(self, payee_id: int) -> PayeeLastUsed | None:
        """Category and tags of this payee's most recent categorised entry.

        Transfers are skipped — they carry no category and say nothing about how
        the payee is normally booked. Rows without a category (split parents) are
        skipped too, so the answer is always usable as a default; ``None`` means
        the payee has nothing to learn from yet.
        """
        stmt = (
            select(Transaction)
            .where(
                Transaction.payee_id == payee_id,
                Transaction.type != TransactionType.TRANSFER,
                Transaction.category_id.is_not(None),
            )
            .options(selectinload(Transaction.tags))
            .order_by(Transaction.date.desc(), Transaction.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        transaction = result.scalars().first()
        if transaction is None:
            return None
        return PayeeLastUsed(
            category_id=transaction.category_id,
            tag_ids=[tag.id for tag in transaction.tags],
        )
