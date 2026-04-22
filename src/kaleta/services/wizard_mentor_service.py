"""Rule-engine for the Getting Started mentor.

Evaluates the current app state against a small set of deterministic rules
and returns short, actionable suggestions (one at a time, in priority order).

Kept intentionally simple for v1 — no LLM, no background scheduling. Each
rule is an ``async`` method returning ``MentorSuggestion | None`` so they
can compose their own queries independently.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.category import Category, CategoryType
from kaleta.models.institution import Institution
from kaleta.models.planned_transaction import PlannedTransaction
from kaleta.models.transaction import Transaction, TransactionType


@dataclass(slots=True, frozen=True)
class MentorSuggestion:
    key: str
    icon: str
    title_key: str
    body_key: str
    cta_key: str
    cta_url: str
    params: dict[str, Any] = field(default_factory=dict)


class WizardMentorService:
    """Returns eligible mentor suggestions for the current app state."""

    # Minimum number of un-categorised transactions before we nudge the user.
    UNCATEGORISED_THRESHOLD = 5
    # Minimum tx count before suggesting planned-transaction setup.
    PLANNED_MIN_TX_COUNT = 20

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def suggestions(self) -> list[MentorSuggestion]:
        """Return the full ordered list of eligible suggestions.

        The view renders only the first one not yet dismissed, but returning
        the list lets callers (tests, future dashboard widget) reason about
        them all.
        """
        found: list[MentorSuggestion] = []
        for rule in (
            self._rule_uncategorised,
            self._rule_no_budget_this_month,
            self._rule_no_planned,
            self._rule_missing_logos,
        ):
            suggestion = await rule()
            if suggestion is not None:
                found.append(suggestion)
        return found

    async def _rule_uncategorised(self) -> MentorSuggestion | None:
        stmt = select(func.count(Transaction.id)).where(
            Transaction.category_id.is_(None),
            Transaction.type != TransactionType.TRANSFER,
        )
        count = (await self.session.execute(stmt)).scalar_one()
        if count <= self.UNCATEGORISED_THRESHOLD:
            return None
        return MentorSuggestion(
            key="uncategorised",
            icon="label_off",
            title_key="wizard.mentor_uncategorised_title",
            body_key="wizard.mentor_uncategorised_body",
            cta_key="wizard.mentor_uncategorised_cta",
            cta_url="/transactions",
            params={"count": count},
        )

    async def _rule_no_budget_this_month(self) -> MentorSuggestion | None:
        today = datetime.date.today()
        expense_cats = (
            await self.session.execute(
                select(func.count(Category.id)).where(Category.type == CategoryType.EXPENSE)
            )
        ).scalar_one()
        if expense_cats == 0:
            return None
        from kaleta.models.budget import Budget

        budgets = (
            await self.session.execute(
                select(func.count(Budget.id)).where(
                    Budget.month == today.month, Budget.year == today.year
                )
            )
        ).scalar_one()
        if budgets > 0:
            return None
        return MentorSuggestion(
            key="no_budget",
            icon="pie_chart",
            title_key="wizard.mentor_no_budget_title",
            body_key="wizard.mentor_no_budget_body",
            cta_key="wizard.mentor_no_budget_cta",
            cta_url="/budgets",
        )

    async def _rule_no_planned(self) -> MentorSuggestion | None:
        tx_count = (await self.session.execute(select(func.count(Transaction.id)))).scalar_one()
        if tx_count < self.PLANNED_MIN_TX_COUNT:
            return None
        planned_count = (
            await self.session.execute(select(func.count(PlannedTransaction.id)))
        ).scalar_one()
        if planned_count > 0:
            return None
        return MentorSuggestion(
            key="no_planned",
            icon="event_repeat",
            title_key="wizard.mentor_no_planned_title",
            body_key="wizard.mentor_no_planned_body",
            cta_key="wizard.mentor_no_planned_cta",
            cta_url="/planned",
        )

    async def _rule_missing_logos(self) -> MentorSuggestion | None:
        total = (await self.session.execute(select(func.count(Institution.id)))).scalar_one()
        if total == 0:
            return None
        missing = (
            await self.session.execute(
                select(func.count(Institution.id)).where(Institution.logo_path.is_(None))
            )
        ).scalar_one()
        if missing == 0:
            return None
        return MentorSuggestion(
            key="missing_logos",
            icon="image",
            title_key="wizard.mentor_logos_title",
            body_key="wizard.mentor_logos_body",
            cta_key="wizard.mentor_logos_cta",
            cta_url="/institutions",
            params={"count": missing},
        )
