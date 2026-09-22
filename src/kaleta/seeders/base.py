# SPDX-License-Identifier: AGPL-3.0-or-later
"""What every example-data seeder is, and the arithmetic they all share.

A seeder owns a slice of the demo dataset and answers three questions: what is
already there (:meth:`Seeder.count`), what it would add (:meth:`Seeder.seed`),
and what it needs first (:attr:`Seeder.depends_on`). Owning the slice is what
makes the whole thing idempotent — a seeder that finds its own rows in place
does nothing rather than doubling them, which is the difference between a
button a user can press twice and one they cannot.

The generator is deterministic: same day, same dataset. That is what lets the
CLI and the Settings button be checked against each other instead of merely
described as equivalent.
"""

from __future__ import annotations

import datetime
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.base import Base

__all__ = [
    "SEED_RANDOM_SEED",
    "SeedOutcome",
    "Seeder",
    "inflation",
    "month_offset",
    "rng",
    "row_count",
    "salary",
    "zloty",
]

#: Pinned so the UI button and the CLI cannot drift apart.
SEED_RANDOM_SEED = 42


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """What one seeder did.

    ``skipped`` is the idempotent case: rows were already there and nothing was
    written. ``counts`` names the tables it touched and how many rows it added,
    which is what the toast and the CLI print.
    """

    key: str
    counts: dict[str, int]
    skipped: bool = False

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class Seeder(ABC):
    """One feature's worth of example data."""

    #: Stable identifier — the storage key, the CLI argument and the i18n stem.
    key: str
    #: Keys that must be seeded before this one can be.
    depends_on: tuple[str, ...] = ()
    #: Material icon for the button in Settings → Data.
    icon: str = "science"

    @property
    def label_key(self) -> str:
        return f"settings.example_data_{self.key}"

    @abstractmethod
    async def count(self, session: AsyncSession) -> int:
        """How many rows of the kind this seeder owns already exist."""

    @abstractmethod
    async def create(self, session: AsyncSession) -> dict[str, int]:
        """Write the rows and report them per table. Called with an empty slice."""

    @abstractmethod
    async def remove(self, session: AsyncSession) -> None:
        """Delete the rows this seeder owns, newest dependants first."""

    async def seed(self, session: AsyncSession, replace: bool = False) -> SeedOutcome:
        """Fill this feature in, or leave it exactly as it is.

        ``replace`` is the only way to overwrite: without it, a feature that
        already holds rows is left alone, so pressing the button twice cannot
        double anyone's example data.

        It removes **this feature's rows only**, which is safe when nothing
        else points at them. Go through ``kaleta.seeders.seed_features`` for
        anything else: it is the one place that knows which other features
        stand on this one and in which order they have to come out.
        """
        if await self.count(session) > 0:
            if not replace:
                return SeedOutcome(key=self.key, counts={}, skipped=True)
            await self.remove(session)
            await session.flush()
        counts = await self.create(session)
        await session.flush()
        return SeedOutcome(key=self.key, counts=counts)


async def row_count(session: AsyncSession, model: type[Base]) -> int:
    """Rows in ``model``'s table."""
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


def rng(salt: int = 0) -> random.Random:
    """A generator pinned to :data:`SEED_RANDOM_SEED`.

    ``salt`` keeps two seeders from drawing the same sequence while each stays
    reproducible on its own — a seeder run alone must produce what it produces
    as part of "Seed everything".
    """
    return random.Random(SEED_RANDOM_SEED + salt)  # nosec B311: demo data, not security


def month_offset(today: datetime.date, n: int) -> tuple[int, int]:
    """``(year, month)`` ``n`` months before ``today``; negative ``n`` looks ahead."""
    total = today.year * 12 + today.month - 1 - n
    return total // 12, total % 12 + 1


def inflation(months_back: int, annual: float = 0.045) -> float:
    """Prices were lower in the past — a factor below 1 for an older month."""
    return float(1.0 / ((1 + annual) ** (months_back / 12)))


def salary(months_back: int, generator: random.Random) -> Decimal:
    """Pay that grows about 5% a year, with a little month-to-month jitter."""
    base = 9000.0 * inflation(months_back, annual=0.05)
    return zloty(base * generator.uniform(0.95, 1.05))


def zloty(amount: float) -> Decimal:
    """A float rounded to the two decimal places money is stored with."""
    return Decimal(str(round(amount, 2)))
