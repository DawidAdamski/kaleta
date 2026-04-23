"""Housekeeping detector + merge flows for duplicate rows.

Three detectors find near-duplicates the user may want to merge:
    * duplicate_transactions — same account + amount + date ± 1 day + similar desc
    * similar_payees        — normalised-name collisions + Levenshtein ≤ 2
    * redundant_categories  — empty categories whose names collide with another

Merge methods reassign every foreign-key reference to the "keeper" row and
delete the rest. Operations are committed atomically.
"""

from __future__ import annotations

import builtins
import datetime
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.budget import Budget
from kaleta.models.category import Category
from kaleta.models.payee import Payee
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.reserve_fund import ReserveFund
from kaleta.models.subscription import Subscription
from kaleta.models.transaction import Transaction, TransactionSplit

# ── Tunables ──────────────────────────────────────────────────────────────────

DUPLICATE_TX_DATE_WINDOW = datetime.timedelta(days=1)
# Scan window for duplicate-transaction detection. Older duplicates are
# unlikely to be actionable and blow up the O(n^2) clustering step.
DUPLICATE_TX_SCAN_DAYS = 365
PAYEE_LEVENSHTEIN_SHORT_NAME_MAX = 10
PAYEE_LEVENSHTEIN_SHORT_THRESHOLD = 2
PAYEE_LEVENSHTEIN_LONG_THRESHOLD = 3


# ── Group shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TxGroupItem:
    id: int
    date: datetime.date
    amount: Decimal
    description: str
    account_id: int | None
    payee_id: int | None
    category_id: int | None


@dataclass(frozen=True)
class TxGroup:
    items: tuple[TxGroupItem, ...]


@dataclass(frozen=True)
class PayeeGroupItem:
    id: int
    name: str
    transaction_count: int


@dataclass(frozen=True)
class PayeeGroup:
    items: tuple[PayeeGroupItem, ...]


@dataclass(frozen=True)
class CategoryGroupItem:
    id: int
    name: str
    parent_id: int | None
    transaction_count: int


@dataclass(frozen=True)
class CategoryGroup:
    items: tuple[CategoryGroupItem, ...]


# ── Service ──────────────────────────────────────────────────────────────────


class DedupeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Duplicate transactions ────────────────────────────────────────────

    async def duplicate_transactions(
        self, *, today: datetime.date | None = None
    ) -> builtins.list[TxGroup]:
        """Find transactions with the same account, amount, near-same date, similar desc.

        Scans only the last ``DUPLICATE_TX_SCAN_DAYS`` days — older duplicates
        are rarely worth merging and make the O(n²) clustering step slow on
        large histories.
        """
        ref = today or datetime.date.today()
        window_start = ref - datetime.timedelta(days=DUPLICATE_TX_SCAN_DAYS)
        # Fetch lightweight rows within the scan window.
        result = await self.session.execute(
            select(
                Transaction.id,
                Transaction.date,
                Transaction.amount,
                Transaction.description,
                Transaction.account_id,
                Transaction.payee_id,
                Transaction.category_id,
            ).where(
                Transaction.is_internal_transfer == False,  # noqa: E712
                Transaction.date >= window_start,
            )
        )
        rows = [
            TxGroupItem(
                id=r.id,
                date=r.date,
                amount=r.amount,
                description=r.description or "",
                account_id=r.account_id,
                payee_id=r.payee_id,
                category_id=r.category_id,
            )
            for r in result.all()
        ]

        # Bucket by (account_id, amount) then compare dates + descriptions.
        buckets: dict[tuple[int | None, Decimal], list[TxGroupItem]] = defaultdict(list)
        for r in rows:
            buckets[(r.account_id, r.amount)].append(r)

        groups: list[TxGroup] = []
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            bucket.sort(key=lambda r: r.date)
            # Greedy cluster: tx within ±1 day AND overlapping desc-key.
            used: set[int] = set()
            for i, r in enumerate(bucket):
                if r.id in used:
                    continue
                cluster = [r]
                for other in bucket[i + 1 :]:
                    if other.id in used:
                        continue
                    if abs((other.date - r.date).days) > DUPLICATE_TX_DATE_WINDOW.days:
                        continue
                    if not _descriptions_look_alike(r.description, other.description):
                        continue
                    cluster.append(other)
                if len(cluster) >= 2:
                    for m in cluster:
                        used.add(m.id)
                    groups.append(TxGroup(items=tuple(cluster)))
        return groups

    async def merge_transactions(
        self, *, keeper_id: int, other_ids: builtins.list[int]
    ) -> int:
        """Delete the non-keeper duplicates. Returns number deleted."""
        deletable = [oid for oid in other_ids if oid != keeper_id]
        if not deletable:
            return 0
        result = await self.session.execute(
            select(Transaction).where(Transaction.id.in_(deletable))
        )
        txs = result.scalars().all()
        for tx in txs:
            await self.session.delete(tx)
        await self.session.commit()
        return len(txs)

    # ── Similar payees ────────────────────────────────────────────────────

    async def similar_payees(self) -> builtins.list[PayeeGroup]:
        """Find payees whose names collide on normalisation or close Levenshtein."""
        # Counts per payee_id for display + keeper-suggestion.
        count_result = await self.session.execute(
            select(
                Transaction.payee_id, func.count(Transaction.id)
            ).group_by(Transaction.payee_id)
        )
        counts: dict[int, int] = {
            pid: cnt for pid, cnt in count_result.all() if pid is not None
        }

        payees_result = await self.session.execute(select(Payee).order_by(Payee.name))
        payees = list(payees_result.scalars().all())
        if len(payees) < 2:
            return []

        # Pass 1: group by normalised key.
        norm_buckets: dict[str, list[Payee]] = defaultdict(list)
        for p in payees:
            key = _normalise_name(p.name)
            if key:
                norm_buckets[key].append(p)

        used: set[int] = set()
        groups: list[PayeeGroup] = []
        for bucket in norm_buckets.values():
            if len(bucket) < 2:
                continue
            groups.append(_make_payee_group(bucket, counts))
            for p in bucket:
                used.add(p.id)

        # Pass 2: Levenshtein pairs among the remainder. Pre-normalise once
        # and skip the inner normalise calls — avoids O(n²) diacritics work.
        remaining = [p for p in payees if p.id not in used]
        norm_cache: list[tuple[Payee, str]] = [
            (p, _normalise_name(p.name)) for p in remaining
        ]
        norm_cache = [(p, n) for p, n in norm_cache if len(n) >= 3]
        visited: set[int] = set()
        for i, (a, na) in enumerate(norm_cache):
            if a.id in visited:
                continue
            cluster = [a]
            for b, nb in norm_cache[i + 1 :]:
                if b.id in visited:
                    continue
                if _norm_levenshtein_close(na, nb):
                    cluster.append(b)
            if len(cluster) >= 2:
                for m in cluster:
                    visited.add(m.id)
                groups.append(_make_payee_group(cluster, counts))
        return groups

    async def merge_payees(
        self, *, keeper_id: int, other_ids: builtins.list[int]
    ) -> int:
        """Reassign every FK reference to keeper, delete the other payees."""
        victims = [oid for oid in other_ids if oid != keeper_id]
        if not victims:
            return 0
        # Reassign Transaction.payee_id
        await self.session.execute(
            update(Transaction)
            .where(Transaction.payee_id.in_(victims))
            .values(payee_id=keeper_id)
        )
        # Reassign Subscription.payee_id
        await self.session.execute(
            update(Subscription)
            .where(Subscription.payee_id.in_(victims))
            .values(payee_id=keeper_id)
        )
        # Delete the victim payees. DismissedCandidate.payee_id → CASCADE.
        result = await self.session.execute(
            select(Payee).where(Payee.id.in_(victims))
        )
        for p in result.scalars().all():
            await self.session.delete(p)
        await self.session.commit()
        return len(victims)

    # ── Redundant categories ──────────────────────────────────────────────

    async def redundant_categories(self) -> builtins.list[CategoryGroup]:
        """Categories whose normalised names collide with another category."""
        count_result = await self.session.execute(
            select(
                Transaction.category_id, func.count(Transaction.id)
            ).group_by(Transaction.category_id)
        )
        counts: dict[int, int] = {
            cid: cnt for cid, cnt in count_result.all() if cid is not None
        }

        cats_result = await self.session.execute(select(Category).order_by(Category.name))
        cats = list(cats_result.scalars().all())
        if len(cats) < 2:
            return []

        buckets: dict[tuple[str, str], list[Category]] = defaultdict(list)
        for c in cats:
            key = _normalise_name(c.name)
            if not key:
                continue
            # Same type so we don't merge income into expense.
            buckets[(key, c.type.value)].append(c)

        groups: list[CategoryGroup] = []
        for bucket in buckets.values():
            if len(bucket) < 2:
                continue
            items = tuple(
                CategoryGroupItem(
                    id=c.id,
                    name=c.name,
                    parent_id=c.parent_id,
                    transaction_count=counts.get(c.id, 0),
                )
                for c in bucket
            )
            groups.append(CategoryGroup(items=items))
        return groups

    async def merge_categories(
        self, *, keeper_id: int, other_ids: builtins.list[int]
    ) -> int:
        """Reassign every FK reference to keeper, delete the other categories.

        Budget rows pointing at victims with a period conflict against the
        keeper's budgets are dropped (keeper's value wins). Nested children
        are re-parented to keeper.
        """
        victims = [oid for oid in other_ids if oid != keeper_id]
        if not victims:
            return 0

        # Budget conflict handling: delete victim budgets whose (month, year)
        # already exists under keeper. Others get reassigned.
        keeper_periods_result = await self.session.execute(
            select(Budget.month, Budget.year).where(Budget.category_id == keeper_id)
        )
        keeper_periods: set[tuple[int, int]] = {
            (m, y) for m, y in keeper_periods_result.all()
        }
        victim_budgets_result = await self.session.execute(
            select(Budget).where(Budget.category_id.in_(victims))
        )
        for b in victim_budgets_result.scalars().all():
            if (b.month, b.year) in keeper_periods:
                await self.session.delete(b)
            else:
                b.category_id = keeper_id
                keeper_periods.add((b.month, b.year))

        # Reassign every other FK reference.
        await self.session.execute(
            update(Transaction)
            .where(Transaction.category_id.in_(victims))
            .values(category_id=keeper_id)
        )
        await self.session.execute(
            update(TransactionSplit)
            .where(TransactionSplit.category_id.in_(victims))
            .values(category_id=keeper_id)
        )
        await self.session.execute(
            update(PlannedTransaction)
            .where(PlannedTransaction.category_id.in_(victims))
            .values(category_id=keeper_id)
        )
        await self.session.execute(
            update(ReserveFund)
            .where(ReserveFund.backing_category_id.in_(victims))
            .values(backing_category_id=keeper_id)
        )
        await self.session.execute(
            update(Subscription)
            .where(Subscription.category_id.in_(victims))
            .values(category_id=keeper_id)
        )
        # Re-parent any child categories pointing at a victim.
        await self.session.execute(
            update(Category)
            .where(Category.parent_id.in_(victims))
            .values(parent_id=keeper_id)
        )

        cats_to_delete_result = await self.session.execute(
            select(Category).where(Category.id.in_(victims))
        )
        for c in cats_to_delete_result.scalars().all():
            await self.session.delete(c)
        await self.session.commit()
        return len(victims)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalise_name(name: str) -> str:
    """Strip diacritics, punctuation, collapse whitespace, lowercase."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    alnum = re.sub(r"[^a-z0-9 ]+", " ", stripped.lower())
    return re.sub(r"\s+", " ", alnum).strip()


def _descriptions_look_alike(a: str, b: str) -> bool:
    """Very lenient: either description is empty, or they share a key token."""
    na = _normalise_name(a)
    nb = _normalise_name(b)
    if not na or not nb:
        return True
    if na == nb:
        return True
    # Share at least one 4+ char token — catches "Netflix /London" vs "Netflix".
    tokens_a = {t for t in na.split() if len(t) >= 4}
    tokens_b = {t for t in nb.split() if len(t) >= 4}
    return bool(tokens_a & tokens_b)


def _levenshtein(a: str, b: str) -> int:
    """Pure-Python Levenshtein distance — fine for short names."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        cur = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[-1] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = cur
    return prev[-1]


def _levenshtein_close(a: str, b: str) -> bool:
    """True when two payee names are close enough to be considered similar.

    Normalises both inputs. For performance-critical callers that have
    pre-normalised the strings, use ``_norm_levenshtein_close``.
    """
    return _norm_levenshtein_close(_normalise_name(a), _normalise_name(b))


def _norm_levenshtein_close(na: str, nb: str) -> bool:
    """Compare two already-normalised strings."""
    if not na or not nb or na == nb:
        return False
    short_len = min(len(na), len(nb))
    threshold = (
        PAYEE_LEVENSHTEIN_SHORT_THRESHOLD
        if short_len <= PAYEE_LEVENSHTEIN_SHORT_NAME_MAX
        else PAYEE_LEVENSHTEIN_LONG_THRESHOLD
    )
    # Fast reject: Levenshtein distance is always >= |len(a) - len(b)|.
    if abs(len(na) - len(nb)) > threshold:
        return False
    # Fast reject: very short strings rarely make meaningful pairs.
    if short_len < 3:
        return False
    return _levenshtein(na, nb) <= threshold


def _make_payee_group(
    bucket: builtins.list[Payee], counts: dict[int, int]
) -> PayeeGroup:
    items = tuple(
        PayeeGroupItem(
            id=p.id, name=p.name, transaction_count=counts.get(p.id, 0)
        )
        for p in bucket
    )
    return PayeeGroup(items=items)


__all__ = [
    "CategoryGroup",
    "CategoryGroupItem",
    "DedupeService",
    "PayeeGroup",
    "PayeeGroupItem",
    "TxGroup",
    "TxGroupItem",
]
