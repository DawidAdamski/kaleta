# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.categorisation_rule import CategorisationRule, RuleMatchMode
from kaleta.models.category import Category
from kaleta.models.payee import Payee
from kaleta.models.transaction import Transaction
from kaleta.schemas.categorisation_rule import (
    CategorisationRuleCreate,
    CategorisationRuleSuggestion,
    CategorisationRuleUpdate,
)

logger = logging.getLogger(__name__)

# Offer a rule after this many identical manual categorisations (BDD KAL-RUL-003).
SUGGESTION_THRESHOLD = 4


class RuleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, active_only: bool = False) -> list[CategorisationRule]:
        stmt = (
            select(CategorisationRule)
            .options(selectinload(CategorisationRule.category))
            .order_by(CategorisationRule.priority.desc(), CategorisationRule.id.asc())
        )
        if active_only:
            stmt = stmt.where(CategorisationRule.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get(self, rule_id: int) -> CategorisationRule | None:
        stmt = (
            select(CategorisationRule)
            .options(selectinload(CategorisationRule.category))
            .where(CategorisationRule.id == rule_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: CategorisationRuleCreate) -> CategorisationRule:
        pattern = data.pattern.strip()
        if not pattern:
            raise ValidationError("Rule pattern must not be empty.")
        await self._require_category(data.category_id)
        if data.match_mode is not RuleMatchMode.CONTAINS:
            raise ValidationError("Only contains match mode is supported.")
        rule = CategorisationRule(
            pattern=pattern,
            match_mode=data.match_mode,
            category_id=data.category_id,
            is_active=data.is_active,
            priority=data.priority,
        )
        self.session.add(rule)
        await self.session.commit()
        loaded = await self.get(rule.id)
        assert loaded is not None
        logger.info("Created categorisation rule id=%s pattern=%r", loaded.id, loaded.pattern)
        return loaded

    async def update(self, rule_id: int, data: CategorisationRuleUpdate) -> CategorisationRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise NotFoundError(f"Categorisation rule {rule_id} not found.")
        updates = data.model_dump(exclude_unset=True)
        if "pattern" in updates:
            pattern = (updates["pattern"] or "").strip()
            if not pattern:
                raise ValidationError("Rule pattern must not be empty.")
            updates["pattern"] = pattern
        if "category_id" in updates and updates["category_id"] is not None:
            await self._require_category(updates["category_id"])
        if (
            "match_mode" in updates
            and updates["match_mode"] is not None
            and updates["match_mode"] is not RuleMatchMode.CONTAINS
        ):
            raise ValidationError("Only contains match mode is supported.")
        for field, value in updates.items():
            setattr(rule, field, value)
        await self.session.commit()
        loaded = await self.get(rule_id)
        assert loaded is not None
        return loaded

    async def delete(self, rule_id: int) -> bool:
        rule = await self.session.get(CategorisationRule, rule_id)
        if rule is None:
            return False
        await self.session.delete(rule)
        await self.session.commit()
        return True

    @staticmethod
    def matches(
        pattern: str,
        *,
        payee_name: str | None,
        description: str,
        match_mode: RuleMatchMode = RuleMatchMode.CONTAINS,
    ) -> bool:
        """Case-insensitive contains; try payee then description."""
        if match_mode is not RuleMatchMode.CONTAINS:
            return False
        needle = pattern.casefold()
        if not needle:
            return False
        if payee_name and needle in payee_name.casefold():
            return True
        return bool(description and needle in description.casefold())

    async def match_category_id(
        self,
        *,
        payee_name: str | None,
        description: str,
    ) -> int | None:
        """Return category_id of the first matching active rule, or None."""
        rules = await self.list(active_only=True)
        for rule in rules:
            if self.matches(
                rule.pattern,
                payee_name=payee_name,
                description=description,
                match_mode=rule.match_mode,
            ):
                return rule.category_id
        return None

    async def suggest_from_corrections(
        self,
        *,
        payee_name: str | None,
        description: str,
        category_id: int,
    ) -> CategorisationRuleSuggestion | None:
        """Offer a rule when the same pattern+category appears often enough.

        Never creates a rule — callers present the offer to the user.
        """
        pattern = self.candidate_pattern(payee_name=payee_name, description=description)
        if pattern is None:
            return None

        existing = await self._find_rule_by_pattern(pattern)
        if existing is not None:
            return None

        match_count = await self._count_matching_categorisations(
            pattern=pattern,
            category_id=category_id,
        )
        if match_count < SUGGESTION_THRESHOLD:
            return None

        category = await self.session.get(Category, category_id)
        if category is None:
            return None

        return CategorisationRuleSuggestion(
            pattern=pattern,
            category_id=category_id,
            category_name=category.name,
            match_count=match_count,
        )

    @staticmethod
    def candidate_pattern(*, payee_name: str | None, description: str) -> str | None:
        """Prefer payee name; fall back to trimmed description."""
        if payee_name and payee_name.strip():
            return payee_name.strip()
        text = description.strip()
        return text or None

    async def _require_category(self, category_id: int) -> Category:
        category = await self.session.get(Category, category_id)
        if category is None:
            raise NotFoundError(f"Category {category_id} not found.")
        return category

    async def _find_rule_by_pattern(self, pattern: str) -> CategorisationRule | None:
        stmt = select(CategorisationRule).where(
            func.lower(CategorisationRule.pattern) == pattern.casefold()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_matching_categorisations(self, *, pattern: str, category_id: int) -> int:
        needle = f"%{pattern.casefold()}%"
        stmt = (
            select(func.count())
            .select_from(Transaction)
            .outerjoin(Payee, Payee.id == Transaction.payee_id)
            .where(
                Transaction.category_id == category_id,
                or_(
                    func.lower(Payee.name).like(needle),
                    func.lower(Transaction.description).like(needle),
                ),
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())
