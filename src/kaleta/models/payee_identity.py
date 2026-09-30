# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates

from kaleta.db.base import Base
from kaleta.models.mixins import TimestampMixin
from kaleta.models.payee import Payee

if TYPE_CHECKING:
    from collections.abc import Iterable

#: Mirrors ``Payee.name``: an identity is a spelling of a payee's name.
PAYEE_IDENTITY_PATTERN_MAX_LENGTH = 200


def identity_key(pattern: str) -> str:
    """The case-insensitive lookup key of a spelling.

    ``casefold`` rather than SQL ``lower()``: SQLite folds ASCII only, so
    "ŻABKA" would never meet "żabka". Runs of whitespace collapse too — bank
    lines pad fields ("LIDL  POZNAN") inconsistently.
    """
    return " ".join(pattern.split()).casefold()


class PayeeIdentity(TimestampMixin, Base):
    """One spelling under which a payee shows up in bank data.

    Banks write the same merchant many ways ("PKO BP", "PKO BANK POLSKI O");
    each spelling the user ties to a payee is an identity, and a transaction
    whose raw payee name matches any of them belongs to that payee. Every
    payee holds at least one — its own name, added when the payee is created.

    Patterns are literal. ``case_sensitive`` identities only match the exact
    spelling; the default compares ``pattern_key``, the casefolded pattern.
    """

    __tablename__ = "payee_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int] = mapped_column(
        ForeignKey("payees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pattern: Mapped[str] = mapped_column(
        String(PAYEE_IDENTITY_PATTERN_MAX_LENGTH), nullable=False, index=True
    )
    pattern_key: Mapped[str] = mapped_column(
        String(PAYEE_IDENTITY_PATTERN_MAX_LENGTH), nullable=False, index=True
    )
    case_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    payee: Mapped[Payee] = relationship("Payee", back_populates="identities")

    @validates("pattern")
    def _derive_key(self, _key: str, value: str) -> str:
        cleaned = " ".join(value.split())
        self.pattern_key = identity_key(cleaned)
        return cleaned

    def matches(self, raw: str) -> bool:
        cleaned = " ".join(raw.split())
        if self.case_sensitive:
            return self.pattern == cleaned
        return self.pattern_key == identity_key(cleaned)

    def __repr__(self) -> str:
        return f"<PayeeIdentity id={self.id} payee_id={self.payee_id} pattern={self.pattern!r}>"


@event.listens_for(Session, "before_flush")
def _give_new_payees_their_name(
    session: Session, _flush_context: object, _instances: Iterable[object] | None
) -> None:
    """Every payee starts with one identity: its own name.

    Done at flush rather than in each service so no creation path — import,
    manual entry, seeders, a merge undo — can leave a payee without one.
    """
    for obj in session.new:
        if isinstance(obj, Payee) and not obj.identities:
            obj.identities.append(PayeeIdentity(pattern=obj.name))
