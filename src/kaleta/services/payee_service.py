# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import builtins

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.db.types import exact_index
from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.payee import Payee
from kaleta.models.payee_identity import PayeeIdentity, identity_index
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.subscription import Subscription
from kaleta.models.transaction import Transaction, TransactionType
from kaleta.schemas.payee import PayeeCreate, PayeeLastUsed, PayeeUpdate
from kaleta.schemas.payee_identity import PayeeIdentityCreate, PayeeIdentityUpdate

#: Mirrors ``Payee.name``'s column width and the schemas' ``max_length``.
PAYEE_NAME_MAX_LENGTH = 200


class PayeeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> builtins.list[Payee]:
        # Sorted here, not in SQL: the name is ciphertext in the database.
        result = await self.session.execute(select(Payee))
        return sorted(result.scalars().all(), key=lambda p: p.name.casefold())

    async def list_with_counts(self) -> builtins.list[tuple[Payee, int]]:
        """Return (payee, tx_count) tuples ordered by name."""
        stmt = (
            select(Payee, func.count(Transaction.id).label("tx_count"))
            .outerjoin(Transaction, Transaction.payee_id == Payee.id)
            .group_by(Payee.id)
        )
        result = await self.session.execute(stmt)
        rows = [(row.Payee, row.tx_count) for row in result]
        return sorted(rows, key=lambda row: row[0].name.casefold())

    async def identities_by_payee(self) -> dict[int, builtins.list[PayeeIdentity]]:
        """Every payee's identities, oldest first, keyed by payee id."""
        result = await self.session.execute(
            select(PayeeIdentity).order_by(PayeeIdentity.payee_id, PayeeIdentity.id)
        )
        grouped: dict[int, builtins.list[PayeeIdentity]] = {}
        for identity in result.scalars().all():
            grouped.setdefault(identity.payee_id, []).append(identity)
        return grouped

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
        old_name = payee.name
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(payee, field, value)
        if payee.name != old_name:
            await self.add_name_identity(payee.id, payee.name)
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
        await self.session.execute(
            update(PlannedTransaction)
            .where(PlannedTransaction.payee_id.in_(merge_ids))
            .values(payee_id=keep_id)
        )
        await self.session.execute(
            update(Subscription)
            .where(Subscription.payee_id.in_(merge_ids))
            .values(payee_id=keep_id)
        )
        await self.absorb_identities(keep_id, merge_ids)
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
            await self.add_name_identity(keep_id, name)
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
            select(Payee.id).where(
                Payee.name_bidx == exact_index(name), Payee.id.not_in([keeper_id, *merged_ids])
            )
        )
        if clash.first() is not None:
            raise ConflictError(f"A payee named '{name}' already exists")
        return keeper

    async def match_or_create_from_name(self, name: str) -> Payee:
        """The payee a raw payee name belongs to; created when nothing matches.

        Used by every path that turns a name into a payee — CSV import and the
        typed name of a manual entry. Precedence:

        1. an identity spelled exactly like *name*;
        2. a case-insensitive identity whose casefolded key equals *name*'s
           (``case_sensitive`` identities are skipped here);
        3. a payee *named* exactly *name* — only reachable when the user has
           edited that name's identity away, and it keeps UNIQUE(name) safe;
        4. otherwise a new payee, which gets its name as its first identity.

        Ties (two payees holding the same spelling in different case, left by
        the migration backfill) go to the oldest identity. Matching is literal
        — no fuzzy matching at import time.

        Does NOT commit — the caller owns the transaction; ``flush()`` makes the
        new ID available within the current session.
        """
        cleaned = " ".join(name.split())
        # An exact spelling has the same key as a case-insensitive one, so the
        # blind index finds both; which of them actually matches is decided on
        # the decrypted patterns below.
        result = await self.session.execute(
            select(PayeeIdentity)
            .where(PayeeIdentity.pattern_key == identity_index(cleaned))
            .order_by(PayeeIdentity.id)
        )
        candidates = builtins.list(result.scalars().all())
        hit = next((i for i in candidates if i.pattern == cleaned), None) or next(
            (i for i in candidates if i.matches(cleaned)), None
        )
        if hit is not None:
            payee = await self.get(hit.payee_id)
            if payee is not None:
                return payee

        named = await self.session.execute(
            select(Payee).where(Payee.name_bidx == exact_index(cleaned))
        )
        existing = named.scalar_one_or_none()
        if existing is not None:
            return existing

        payee = Payee(name=cleaned)
        self.session.add(payee)
        await self.session.flush()
        return payee

    # ── Identities ────────────────────────────────────────────────────────

    async def list_identities(self, payee_id: int) -> builtins.list[PayeeIdentity]:
        if await self.get(payee_id) is None:
            raise NotFoundError("Payee not found")
        result = await self.session.execute(
            select(PayeeIdentity)
            .where(PayeeIdentity.payee_id == payee_id)
            .order_by(PayeeIdentity.id)
        )
        return builtins.list(result.scalars().all())

    async def add_identity(self, payee_id: int, data: PayeeIdentityCreate) -> PayeeIdentity:
        """Tie another spelling to a payee.

        A spelling another payee already answers to is a conflict: one raw
        name must lead to one payee.
        """
        if await self.get(payee_id) is None:
            raise NotFoundError("Payee not found")
        await self._check_spelling_free(data.pattern, payee_id=payee_id)
        identity = PayeeIdentity(
            payee_id=payee_id, pattern=data.pattern, case_sensitive=data.case_sensitive
        )
        self.session.add(identity)
        await self.session.commit()
        await self.session.refresh(identity)
        return identity

    async def update_identity(
        self, payee_id: int, identity_id: int, data: PayeeIdentityUpdate
    ) -> PayeeIdentity:
        identity = await self._get_identity(payee_id, identity_id)
        if data.pattern is not None and data.pattern != identity.pattern:
            await self._check_spelling_free(
                data.pattern, payee_id=payee_id, ignore_identity_id=identity_id
            )
            identity.pattern = data.pattern
        if data.case_sensitive is not None:
            identity.case_sensitive = data.case_sensitive
        await self.session.commit()
        await self.session.refresh(identity)
        return identity

    async def delete_identity(self, payee_id: int, identity_id: int) -> None:
        """Remove one spelling. The last one cannot go — delete the payee instead."""
        identity = await self._get_identity(payee_id, identity_id)
        count = await self.session.scalar(
            select(func.count(PayeeIdentity.id)).where(PayeeIdentity.payee_id == payee_id)
        )
        if (count or 0) <= 1:
            raise ConflictError(
                "A payee needs at least one identity; delete the payee instead",
                code="last_identity",
            )
        await self.session.delete(identity)
        await self.session.commit()

    async def absorb_identities(
        self, keeper_id: int, merged_ids: builtins.list[int]
    ) -> builtins.list[int]:
        """Move the merged payees' identities onto the keeper, before they are deleted.

        Spellings the keeper already answers to are dropped rather than
        duplicated. Returns the ids of the identities that moved. Does NOT
        commit — it is one step of a merge.
        """
        if not merged_ids:
            return []
        result = await self.session.execute(
            select(PayeeIdentity)
            .where(PayeeIdentity.payee_id.in_([keeper_id, *merged_ids]))
            .order_by(PayeeIdentity.id)
        )
        rows = builtins.list(result.scalars().all())
        held = {_spelling(i) for i in rows if i.payee_id == keeper_id}
        moved: builtins.list[int] = []
        for identity in rows:
            if identity.payee_id == keeper_id:
                continue
            if _spelling(identity) in held:
                await self.session.delete(identity)
                continue
            identity.payee_id = keeper_id
            held.add(_spelling(identity))
            moved.append(identity.id)
        await self.session.flush()
        # A merged payee's loaded ``identities`` collection still lists the
        # rows that just moved; deleting the payee would cascade into them.
        for obj in builtins.list(self.session.identity_map.values()):
            if isinstance(obj, Payee) and obj.id in merged_ids:
                self.session.expire(obj, ["identities"])
        return moved

    async def _get_identity(self, payee_id: int, identity_id: int) -> PayeeIdentity:
        identity = await self.session.get(PayeeIdentity, identity_id)
        if identity is None or identity.payee_id != payee_id:
            raise NotFoundError("Payee identity not found")
        return identity

    async def _check_spelling_free(
        self, pattern: str, *, payee_id: int, ignore_identity_id: int | None = None
    ) -> None:
        stmt = select(PayeeIdentity).where(PayeeIdentity.pattern_key == identity_index(pattern))
        if ignore_identity_id is not None:
            stmt = stmt.where(PayeeIdentity.id != ignore_identity_id)
        clash = (await self.session.execute(stmt)).scalars().first()
        if clash is None:
            return
        if clash.payee_id == payee_id:
            raise ConflictError(f"This payee already has the identity '{clash.pattern}'")
        owner = await self.get(clash.payee_id)
        owner_name = owner.name if owner is not None else str(clash.payee_id)
        raise ConflictError(f"'{pattern}' is already an identity of payee '{owner_name}'")

    async def add_name_identity(self, payee_id: int, name: str) -> None:
        """After a rename, the new name becomes a spelling too — unless someone holds it.

        The old spelling stays: bank lines still arrive under it.
        """
        taken = await self.session.execute(
            select(PayeeIdentity.id).where(PayeeIdentity.pattern_key == identity_index(name))
        )
        if taken.first() is None:
            self.session.add(PayeeIdentity(payee_id=payee_id, pattern=name))

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


def _spelling(identity: PayeeIdentity) -> tuple[bool, str]:
    """What an identity matches: its exact pattern, or its casefolded key."""
    if identity.case_sensitive:
        return True, identity.pattern
    return False, identity.pattern_key
