# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class DismissedCandidateKind(enum.StrEnum):
    """Which detector produced the pattern the user waved away.

    One dismissal concept serves both detectors; the kind keeps a
    "not a subscription" decision from also silencing the radar.
    """

    SUBSCRIPTION = "subscription"
    UNPLANNED = "unplanned"


class DismissedCandidate(TimestampMixin, Base):
    """A recurring-charge pattern the user has chosen to ignore.

    The subscription detector and the unplanned-expenses radar surface
    candidates from transaction history; this table records "no thanks, stop
    suggesting that" so those patterns don't reappear on every page load.
    One row per (kind, source, amount-bucket).

    Source is either a Payee (payee_id set, merchant_key null) or a
    description-derived merchant key (merchant_key set, payee_id null).
    """

    __tablename__ = "dismissed_candidate_patterns"
    __table_args__ = (
        UniqueConstraint(
            "payee_id",
            "merchant_key",
            "amount_bucket",
            "kind",
            name="uq_dismissed_candidate_pattern",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=True
    )
    merchant_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount_bucket: Mapped[str] = mapped_column(String(30), nullable=False)
    kind: Mapped[DismissedCandidateKind] = mapped_column(
        SAEnum(DismissedCandidateKind, native_enum=False),
        nullable=False,
        default=DismissedCandidateKind.SUBSCRIPTION,
        server_default=DismissedCandidateKind.SUBSCRIPTION.name,
    )

    def __repr__(self) -> str:
        return (
            f"<DismissedCandidate id={self.id} kind={self.kind} "
            f"payee_id={self.payee_id} merchant_key={self.merchant_key!r} "
            f"amount_bucket={self.amount_bucket!r}>"
        )
