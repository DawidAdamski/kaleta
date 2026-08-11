# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import fnmatch
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.exceptions import NotFoundError, ValidationError
from kaleta.models.account import Account
from kaleta.models.import_rule import ImportRule
from kaleta.schemas.import_rule import ImportRuleCreate, ImportRuleUpdate

logger = logging.getLogger(__name__)

# First run of digits (and any trailing digit/hyphen digit groups) → `*`.
_DIGIT_BLOCK = re.compile(r"\d[\d\-]*")


class ImportRuleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, active_only: bool = False) -> list[ImportRule]:
        stmt = (
            select(ImportRule)
            .options(selectinload(ImportRule.account))
            .order_by(ImportRule.filename_pattern.asc(), ImportRule.id.asc())
        )
        if active_only:
            stmt = stmt.where(ImportRule.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get(self, rule_id: int) -> ImportRule | None:
        stmt = (
            select(ImportRule)
            .options(selectinload(ImportRule.account))
            .where(ImportRule.id == rule_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: ImportRuleCreate) -> ImportRule:
        pattern = self._normalise_pattern(data.filename_pattern)
        await self._require_account(data.account_id)
        rule = ImportRule(
            filename_pattern=pattern,
            account_id=data.account_id,
            column_mapping=dict(data.column_mapping),
            encoding=data.encoding,
            delimiter=data.delimiter,
            is_active=data.is_active,
        )
        self.session.add(rule)
        await self.session.commit()
        loaded = await self.get(rule.id)
        assert loaded is not None
        logger.info(
            "Created import rule id=%s pattern=%r account_id=%s",
            loaded.id,
            loaded.filename_pattern,
            loaded.account_id,
        )
        return loaded

    async def update(self, rule_id: int, data: ImportRuleUpdate) -> ImportRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise NotFoundError(f"Import rule {rule_id} not found.")
        updates = data.model_dump(exclude_unset=True)
        if "filename_pattern" in updates:
            updates["filename_pattern"] = self._normalise_pattern(updates["filename_pattern"] or "")
        if "account_id" in updates and updates["account_id"] is not None:
            await self._require_account(updates["account_id"])
        if "column_mapping" in updates and updates["column_mapping"] is not None:
            updates["column_mapping"] = dict(updates["column_mapping"])
        for field, value in updates.items():
            setattr(rule, field, value)
        await self.session.commit()
        loaded = await self.get(rule_id)
        assert loaded is not None
        return loaded

    async def delete(self, rule_id: int) -> bool:
        rule = await self.session.get(ImportRule, rule_id)
        if rule is None:
            return False
        await self.session.delete(rule)
        await self.session.commit()
        return True

    async def match(self, filename: str) -> ImportRule | None:
        """Return the best active rule for ``filename``, or None.

        Specificity: longer non-wildcard prefix wins. Ties broken by
        ``last_used_at`` descending (missing treated as oldest), then id.
        Matching is case-insensitive.
        """
        rules = await self.list(active_only=True)
        matches = [r for r in rules if self.pattern_matches(r.filename_pattern, filename)]
        if not matches:
            return None
        matches.sort(
            key=lambda r: (
                self.specificity_score(r.filename_pattern),
                self._aware_last_used(r.last_used_at),
                r.id,
            ),
            reverse=True,
        )
        return matches[0]

    async def touch_last_used(self, rule_id: int) -> None:
        rule = await self.session.get(ImportRule, rule_id)
        if rule is None:
            return
        rule.last_used_at = datetime.now(UTC)
        await self.session.commit()

    async def upsert_from_import(
        self,
        *,
        filename: str,
        filename_pattern: str | None,
        account_id: int,
        column_mapping: dict[str, Any],
        encoding: str | None = None,
        delimiter: str | None = None,
    ) -> ImportRule:
        """Create or update a rule after a successful import (remember mapping)."""
        pattern = self._normalise_pattern(
            filename_pattern or self.suggest_filename_pattern(filename)
        )
        existing = await self._find_by_pattern(pattern)
        if existing is None:
            return await self.create(
                ImportRuleCreate(
                    filename_pattern=pattern,
                    account_id=account_id,
                    column_mapping=column_mapping,
                    encoding=encoding,
                    delimiter=delimiter,
                    is_active=True,
                )
            )
        updated = await self.update(
            existing.id,
            ImportRuleUpdate(
                account_id=account_id,
                column_mapping=column_mapping,
                encoding=encoding,
                delimiter=delimiter,
                is_active=True,
            ),
        )
        await self.touch_last_used(updated.id)
        refreshed = await self.get(updated.id)
        assert refreshed is not None
        return refreshed

    @staticmethod
    def suggest_filename_pattern(filename: str) -> str:
        """Replace the first digit block with ``*`` — ``mbank-2025-10.csv`` → ``mbank-*.csv``."""
        name = filename.strip()
        if not name:
            return "*"
        if _DIGIT_BLOCK.search(name):
            return _DIGIT_BLOCK.sub("*", name, count=1)
        return name

    @staticmethod
    def specificity_score(pattern: str) -> int:
        """Length of the leading non-wildcard prefix (case-folded)."""
        folded = pattern.casefold()
        star = folded.find("*")
        question = folded.find("?")
        cut = len(folded)
        if star >= 0:
            cut = min(cut, star)
        if question >= 0:
            cut = min(cut, question)
        return cut

    @staticmethod
    def pattern_matches(pattern: str, filename: str) -> bool:
        return fnmatch.fnmatchcase(filename.casefold(), pattern.casefold())

    @staticmethod
    def _aware_last_used(value: datetime | None) -> datetime:
        """SQLite may return naive datetimes; normalise for sort comparisons."""
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    async def _find_by_pattern(self, pattern: str) -> ImportRule | None:
        folded = pattern.casefold()
        rules = await self.list()
        for rule in rules:
            if rule.filename_pattern.casefold() == folded:
                return rule
        return None

    async def _require_account(self, account_id: int) -> Account:
        account = await self.session.get(Account, account_id)
        if account is None:
            raise NotFoundError(f"Account {account_id} not found.")
        return account

    @staticmethod
    def _normalise_pattern(pattern: str) -> str:
        cleaned = pattern.strip()
        if not cleaned:
            raise ValidationError("Import rule filename pattern must not be empty.")
        if len(cleaned) > 200:
            raise ValidationError("Import rule filename pattern is too long.")
        return cleaned
