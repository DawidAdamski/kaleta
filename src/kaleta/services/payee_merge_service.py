# SPDX-License-Identifier: AGPL-3.0-or-later
"""Merge proposals for near-duplicate payees, and automatic merges with undo.

Where :class:`~kaleta.services.dedupe_service.DedupeService` groups payees by
hard rules (same normalised name, same core name, small edit distance), this
service *scores* every pair of payees on a 0–1 scale and ranks them:

    score = 0.5 · name similarity
          + 0.3 · best similarity between any two of their identities
          + 0.2 · overlap of their merchant keys (first word of each spelling)

Similarities are ``1 − Levenshtein / longer length`` on normalised text
(lowercase, no diacritics, no punctuation). Pairs at or above
:data:`PROPOSAL_THRESHOLD` are proposed; a scan with auto-merge on merges the
pairs at or above the user's threshold outright and logs each merge so it
can be undone for :data:`UNDO_WINDOW`.
"""

from __future__ import annotations

import builtins
import datetime
import functools
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.exceptions import ConflictError, NotFoundError, ValidationError
from kaleta.models.payee import Payee
from kaleta.models.payee_identity import PayeeIdentity
from kaleta.models.payee_merge import DismissedPayeeMerge, PayeeAutoMerge
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.subscription import Subscription
from kaleta.models.transaction import Transaction
from kaleta.schemas.payee_identity import PayeeMergeReason
from kaleta.services.dedupe_service import DedupeService, _levenshtein, _normalise_name
from kaleta.services.payee_service import PayeeService

# ── Tunables ──────────────────────────────────────────────────────────────────

WEIGHT_NAME = 0.5
WEIGHT_IDENTITY = 0.3
WEIGHT_MERCHANT_KEY = 0.2
#: Below this a pair is not worth the user's attention.
PROPOSAL_THRESHOLD = 0.75
DEFAULT_AUTO_MERGE_THRESHOLD = 0.92
AUTO_MERGE_THRESHOLD_MIN = 0.80
AUTO_MERGE_THRESHOLD_MAX = 0.99
#: How long an automatic merge can be taken back.
UNDO_WINDOW = datetime.timedelta(days=7)

#: What undo gives back to a merged payee, besides its identities and rows.
_PAYEE_FIELDS = (
    "name",
    "website",
    "address",
    "city",
    "country",
    "email",
    "phone",
    "notes",
    "user_id",
)


# ── Shapes ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MergeProposal:
    """Two payees scored as one merchant. ``left`` is the one a merge keeps."""

    left_id: int
    left_name: str
    right_id: int
    right_name: str
    score: float
    reason: PayeeMergeReason


@dataclass(frozen=True)
class AutoMergeEntry:
    """A logged automatic merge, as the "Recently merged" list shows it."""

    id: int
    keeper_id: int
    keeper_name: str
    merged_name: str
    score: float
    merged_at: datetime.datetime


@dataclass(frozen=True)
class MergeScanResult:
    merged: builtins.list[AutoMergeEntry]
    proposals: builtins.list[MergeProposal]


@dataclass(frozen=True)
class _Candidate:
    id: int
    name: str
    norm_name: str
    norm_spellings: tuple[str, ...]
    merchant_keys: frozenset[str]
    tx_count: int
    created_at: datetime.datetime

    def keeper_rank(self) -> tuple[int, datetime.datetime, int]:
        """Sorts the payee a merge should keep first: most used, then oldest."""
        return (-self.tx_count, _aware(self.created_at), self.id)


# ── Service ───────────────────────────────────────────────────────────────────


class PayeeMergeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Proposals ─────────────────────────────────────────────────────────

    async def propose_merges(
        self, *, min_score: float = PROPOSAL_THRESHOLD
    ) -> builtins.list[MergeProposal]:
        """Every undismissed pair of payees scoring at least *min_score*, best first."""
        candidates = await self._candidates()
        dismissed = await self._dismissed_pairs()
        proposals: builtins.list[MergeProposal] = []
        for i, a in enumerate(candidates):
            for b in candidates[i + 1 :]:
                if _pair(a.id, b.id) in dismissed:
                    continue
                scored = _score(a, b, min_score)
                if scored is None:
                    continue
                score, reason = scored
                keep, other = sorted((a, b), key=_Candidate.keeper_rank)
                proposals.append(
                    MergeProposal(
                        left_id=keep.id,
                        left_name=keep.name,
                        right_id=other.id,
                        right_name=other.name,
                        score=round(score, 4),
                        reason=reason,
                    )
                )
        proposals.sort(key=lambda p: (-p.score, p.left_name, p.right_name))
        return proposals

    async def dismiss(self, left_id: int, right_id: int) -> None:
        """Stop proposing this pair. Dismissing twice is harmless."""
        if left_id == right_id:
            raise ValidationError("A payee cannot be paired with itself")
        for payee_id in (left_id, right_id):
            if await self.session.get(Payee, payee_id) is None:
                raise NotFoundError("Payee not found")
        first, second = _pair(left_id, right_id)
        existing = await self.session.execute(
            select(DismissedPayeeMerge.id).where(
                DismissedPayeeMerge.first_payee_id == first,
                DismissedPayeeMerge.second_payee_id == second,
            )
        )
        if existing.first() is None:
            self.session.add(DismissedPayeeMerge(first_payee_id=first, second_payee_id=second))
            await self.session.commit()

    # ── Scan + automatic merge ────────────────────────────────────────────

    async def scan(self, *, auto_merge_threshold: float | None = None) -> MergeScanResult:
        """Score all pairs; with a threshold, merge those at or above it.

        ``None`` means auto-merge is off: the scan only proposes. Pairs are
        merged best first; a payee already merged away in this scan is not
        merged again, so a chain A≈B≈C folds into the strongest keeper only.
        """
        proposals = await self.propose_merges()
        if auto_merge_threshold is None:
            return MergeScanResult(merged=[], proposals=proposals)
        if not AUTO_MERGE_THRESHOLD_MIN <= auto_merge_threshold <= AUTO_MERGE_THRESHOLD_MAX:
            raise ValidationError(
                f"Auto-merge threshold must be between {AUTO_MERGE_THRESHOLD_MIN} "
                f"and {AUTO_MERGE_THRESHOLD_MAX}"
            )
        consumed: set[int] = set()
        record_ids: builtins.list[int] = []
        for proposal in proposals:
            if proposal.score < auto_merge_threshold:
                break
            if proposal.left_id in consumed or proposal.right_id in consumed:
                continue
            record_ids.append(
                await self._auto_merge(proposal.left_id, proposal.right_id, proposal.score)
            )
            consumed.add(proposal.right_id)
        if not record_ids:
            return MergeScanResult(merged=[], proposals=proposals)
        merged = [e for e in await self.recent_auto_merges() if e.id in record_ids]
        return MergeScanResult(merged=merged, proposals=await self.propose_merges())

    async def recent_auto_merges(
        self, *, now: datetime.datetime | None = None
    ) -> builtins.list[AutoMergeEntry]:
        """Automatic merges still inside the undo window, newest first."""
        cutoff = (now or datetime.datetime.now(datetime.UTC)) - UNDO_WINDOW
        result = await self.session.execute(
            select(PayeeAutoMerge, Payee.name)
            .join(Payee, Payee.id == PayeeAutoMerge.keeper_id)
            .where(PayeeAutoMerge.undone_at.is_(None))
            .order_by(PayeeAutoMerge.id.desc())
        )
        return [
            AutoMergeEntry(
                id=record.id,
                keeper_id=record.keeper_id,
                keeper_name=keeper_name,
                merged_name=record.merged_name,
                score=record.score,
                merged_at=_aware(record.created_at),
            )
            for record, keeper_name in result.all()
            if _aware(record.created_at) >= cutoff
        ]

    async def undo(self, record_id: int, *, now: datetime.datetime | None = None) -> Payee:
        """Bring an automatically merged payee back, with what the merge took from it.

        The payee returns with its own fields and the identities it handed
        over; the rows the merge re-pointed at the keeper go back to it unless
        the user has since moved them elsewhere. Rows the keeper gained after
        the merge stay with the keeper.
        """
        moment = now or datetime.datetime.now(datetime.UTC)
        record = await self.session.get(PayeeAutoMerge, record_id)
        if record is None or record.undone_at is not None:
            raise NotFoundError("Automatic merge not found")
        if moment - _aware(record.created_at) > UNDO_WINDOW:
            raise ConflictError("This merge is older than 7 days and can no longer be undone")
        keeper_id = record.keeper_id
        snapshot: dict[str, Any] = record.snapshot
        fields: dict[str, Any] = snapshot["fields"]
        clash = await self.session.execute(select(Payee.id).where(Payee.name == fields["name"]))
        if clash.first() is not None:
            raise ConflictError(f"A payee named '{fields['name']}' already exists")

        identities = await self.session.execute(
            select(PayeeIdentity).where(
                PayeeIdentity.id.in_(snapshot["identity_ids"]),
                PayeeIdentity.payee_id == keeper_id,
            )
        )
        restored = Payee(**fields)
        restored.identities = builtins.list(identities.scalars().all())
        self.session.add(restored)
        await self.session.flush()

        for model, key in (
            (Transaction, "transaction_ids"),
            (PlannedTransaction, "planned_transaction_ids"),
            (Subscription, "subscription_ids"),
        ):
            ids = snapshot[key]
            if ids:
                await self.session.execute(
                    update(model)
                    .where(model.id.in_(ids), model.payee_id == keeper_id)
                    .values(payee_id=restored.id)
                )
        record.undone_at = moment
        await self.session.commit()
        await self.session.refresh(restored)
        return restored

    async def _auto_merge(self, keeper_id: int, merged_id: int, score: float) -> int:
        """Merge *merged_id* into *keeper_id*, logging what undo needs. Commits."""
        merged = await self.session.get(Payee, merged_id)
        if merged is None:
            raise NotFoundError("Payee not found")
        snapshot: dict[str, Any] = {
            "fields": {field: getattr(merged, field) for field in _PAYEE_FIELDS},
            "transaction_ids": await self._ids_of(Transaction, merged_id),
            "planned_transaction_ids": await self._ids_of(PlannedTransaction, merged_id),
            "subscription_ids": await self._ids_of(Subscription, merged_id),
        }
        snapshot["identity_ids"] = await PayeeService(self.session).absorb_identities(
            keeper_id, [merged_id]
        )
        record = PayeeAutoMerge(
            keeper_id=keeper_id, merged_name=merged.name, score=score, snapshot=snapshot
        )
        self.session.add(record)
        await self.session.flush()
        record_id = record.id
        # One commit for the log and the merge: an undo record never
        # outlives a merge that failed, nor the other way round.
        await DedupeService(self.session).merge_payees(keeper_id=keeper_id, other_ids=[merged_id])
        return record_id

    async def _ids_of(
        self,
        model: type[Transaction] | type[PlannedTransaction] | type[Subscription],
        payee_id: int,
    ) -> builtins.list[int]:
        result = await self.session.execute(select(model.id).where(model.payee_id == payee_id))
        return [row_id for (row_id,) in result.all()]

    # ── Loading ───────────────────────────────────────────────────────────

    async def _candidates(self) -> builtins.list[_Candidate]:
        counts_result = await self.session.execute(
            select(Transaction.payee_id, func.count(Transaction.id)).group_by(Transaction.payee_id)
        )
        counts: dict[int, int] = {pid: cnt for pid, cnt in counts_result.all() if pid is not None}
        spellings: dict[int, builtins.list[str]] = {}
        identity_result = await self.session.execute(
            select(PayeeIdentity.payee_id, PayeeIdentity.pattern).order_by(PayeeIdentity.id)
        )
        for payee_id, pattern in identity_result.all():
            spellings.setdefault(payee_id, []).append(pattern)
        payees = await self.session.execute(select(Payee).order_by(Payee.id))
        candidates: builtins.list[_Candidate] = []
        for payee in payees.scalars().all():
            norm_name = _normalise_name(payee.name)
            norm_spellings = tuple(
                dict.fromkeys(
                    n
                    for n in (norm_name, *(_normalise_name(s) for s in spellings.get(payee.id, [])))
                    if n
                )
            )
            if not norm_spellings:
                continue
            candidates.append(
                _Candidate(
                    id=payee.id,
                    name=payee.name,
                    norm_name=norm_name,
                    norm_spellings=norm_spellings,
                    merchant_keys=frozenset(s.split()[0] for s in norm_spellings),
                    tx_count=counts.get(payee.id, 0),
                    created_at=payee.created_at,
                )
            )
        return candidates

    async def _dismissed_pairs(self) -> set[tuple[int, int]]:
        result = await self.session.execute(
            select(DismissedPayeeMerge.first_payee_id, DismissedPayeeMerge.second_payee_id)
        )
        return {(first, second) for first, second in result.all()}


# ── Scoring ───────────────────────────────────────────────────────────────────


def similarity(a: str, b: str) -> float:
    """``1 − Levenshtein(a, b) / len(longer)`` on already-normalised strings."""
    if not a or not b:
        return 0.0
    longest = max(len(a), len(b))
    return 1.0 - _levenshtein(a, b) / longest


def _similarity_ceiling(a: str, b: str) -> float:
    """A cheap upper bound of :func:`similarity`.

    The bag distance (characters one string has that the other lacks, as
    multisets) never exceeds the edit distance, so this lets the O(n²) pair
    loop skip most pairs without running Levenshtein.
    """
    if not a or not b:
        return 0.0
    ca, cb = _bag(a), _bag(b)
    bag = max(sum((ca - cb).values()), sum((cb - ca).values()))
    return 1.0 - bag / max(len(a), len(b))


@functools.lru_cache(maxsize=4096)
def _bag(text: str) -> Counter[str]:
    """Character multiset of a spelling; cached, as each one meets every other."""
    return Counter(text)


def _best_similarity(a: tuple[str, ...], b: tuple[str, ...], floor: float) -> float:
    """The closest pair of spellings; pairs that cannot beat *floor* are skipped."""
    best = 0.0
    for x in a:
        for y in b:
            if _similarity_ceiling(x, y) <= max(best, floor):
                continue
            best = max(best, similarity(x, y))
            if best == 1.0:
                return best
    return best


def _score(a: _Candidate, b: _Candidate, min_score: float) -> tuple[float, PayeeMergeReason] | None:
    keys_union = a.merchant_keys | b.merchant_keys
    merchant = len(a.merchant_keys & b.merchant_keys) / len(keys_union) if keys_union else 0.0
    merchant_part = WEIGHT_MERCHANT_KEY * merchant
    # Identity similarity is at least the name similarity (the name is one of
    # the spellings), so the name ceiling bounds the whole score.
    name_ceiling = _similarity_ceiling(a.norm_name, b.norm_name)
    best_spelling_ceiling = max(
        (_similarity_ceiling(x, y) for x in a.norm_spellings for y in b.norm_spellings),
        default=0.0,
    )
    if (
        WEIGHT_NAME * name_ceiling + WEIGHT_IDENTITY * best_spelling_ceiling + merchant_part
        < min_score
    ):
        return None
    name = similarity(a.norm_name, b.norm_name)
    identity_floor = (min_score - WEIGHT_NAME * name - merchant_part) / WEIGHT_IDENTITY
    identity = max(name, _best_similarity(a.norm_spellings, b.norm_spellings, identity_floor))
    score = WEIGHT_NAME * name + WEIGHT_IDENTITY * identity + merchant_part
    if score < min_score:
        return None
    parts = {
        PayeeMergeReason.NAME: WEIGHT_NAME * name,
        PayeeMergeReason.IDENTITY: WEIGHT_IDENTITY * identity,
        PayeeMergeReason.MERCHANT_KEY: merchant_part,
    }
    return score, max(parts, key=lambda reason: parts[reason])


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _aware(moment: datetime.datetime) -> datetime.datetime:
    """SQLite hands timestamps back naive; they were written in UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=datetime.UTC)


__all__ = [
    "AUTO_MERGE_THRESHOLD_MAX",
    "AUTO_MERGE_THRESHOLD_MIN",
    "DEFAULT_AUTO_MERGE_THRESHOLD",
    "PROPOSAL_THRESHOLD",
    "UNDO_WINDOW",
    "AutoMergeEntry",
    "MergeProposal",
    "MergeScanResult",
    "PayeeMergeService",
    "similarity",
]
