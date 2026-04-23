from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin


class DismissedCandidate(TimestampMixin, Base):
    """A recurring-charge pattern the user has chosen to ignore.

    The subscription detector surfaces candidates from transaction history;
    this table records "no thanks, stop suggesting that" so those patterns
    don't reappear on every page load. One row per (source, amount-bucket).

    Source is either a Payee (payee_id set, merchant_key null) or a
    description-derived merchant key (merchant_key set, payee_id null).
    """

    __tablename__ = "dismissed_candidate_patterns"
    __table_args__ = (
        UniqueConstraint(
            "payee_id",
            "merchant_key",
            "amount_bucket",
            name="uq_dismissed_candidate_pattern",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=True
    )
    merchant_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount_bucket: Mapped[str] = mapped_column(String(30), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<DismissedCandidate id={self.id} "
            f"payee_id={self.payee_id} merchant_key={self.merchant_key!r} "
            f"amount_bucket={self.amount_bucket!r}>"
        )
