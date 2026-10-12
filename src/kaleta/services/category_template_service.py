# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply category templates — a described life, merged into the tree (``category-templates``).

The catalogue is TOML data under ``kaleta/data/category_templates`` (``CategoryTemplate``
schema). Applying a template adds its parent/child categories, merging by blind index so a
parent shared with another template (or an earlier run) is reused, never duplicated. A
repeatable template (a car, a company) takes a per-copy name so "Samochód" becomes
"Samochód: Skoda" and each copy is its own subtree. The Company template also seeds its
business purposes under the Subscriptions tree (ADR-28, #219).
"""

from __future__ import annotations

import builtins
import tomllib
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.types import exact_index
from kaleta.exceptions import NotFoundError
from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category_template import (
    CategoryTemplate,
    TemplateApplyResult,
    TemplateGroup,
    TemplatePreviewResult,
    TemplatePreviewRow,
    TemplateSelection,
)
from kaleta.services.category_service import CategoryService

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data" / "category_templates"


@lru_cache(maxsize=1)
def _catalogue() -> dict[str, CategoryTemplate]:
    """Load and validate every ``*.toml`` template once, keyed by ``key``."""
    templates: dict[str, CategoryTemplate] = {}
    for path in sorted(_TEMPLATE_DIR.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        template = CategoryTemplate.model_validate(data)
        templates[template.key] = template
    return templates


class CategoryTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def list() -> builtins.list[CategoryTemplate]:
        """Every template, in picker order."""
        return sorted(_catalogue().values(), key=lambda t: (t.order, t.key))

    @staticmethod
    def get(key: str) -> CategoryTemplate:
        template = _catalogue().get(key)
        if template is None:
            raise NotFoundError(f"Category template not found: {key}")
        return template

    @staticmethod
    def _suffix(template: CategoryTemplate, selection: TemplateSelection) -> str:
        # Strip first: a blank copy_name must not make the suffix ": " (and merge every
        # copy into one tree under "Samochód: ").
        name = (selection.copy_name or "").strip()
        return f": {name}" if template.repeatable and name else ""

    @staticmethod
    def _subscriptions_label(language: str) -> str:
        return "Subskrypcje" if language.startswith("pl") else "Subscriptions"

    # ── Preview ───────────────────────────────────────────────────────────

    async def preview(
        self, selections: builtins.list[TemplateSelection], *, language: str = "pl"
    ) -> TemplatePreviewResult:
        """What applying *selections* (in order) would add, without changing anything.

        A category counted as added once is not counted again for a later selection that
        names it too, so two cars adding "Paliwo" under *different* parents both read as
        additions, while two templates sharing a parent read it once. ``planned`` is keyed
        on the category's name-path, not a DB id, because a not-yet-created parent has no id.
        """
        rows: builtins.list[TemplatePreviewRow] = []
        planned: set[tuple[str, ...]] = set()
        subs_label = self._subscriptions_label(language)
        for selection in selections:
            template = self.get(selection.key)
            suffix = self._suffix(template, selection)
            for group in template.groups:
                parent_name = group.parent_name(language) + suffix
                parent_key = ("root", parent_name, group.type.value)
                parent_id = await self._find_root_id(parent_name, group.type)
                parent_exists = parent_id is not None or parent_key in planned
                planned.add(parent_key)
                rows.append(
                    TemplatePreviewRow(label=parent_name, type=group.type, exists=parent_exists)
                )
                for child in group.child_names(language):
                    child_key = ("child", parent_name, child, group.type.value)
                    child_exists = (
                        parent_id is not None
                        and await self._find_child_id(parent_id, child) is not None
                    ) or child_key in planned
                    planned.add(child_key)
                    rows.append(
                        TemplatePreviewRow(
                            label=f"{parent_name} → {child}",
                            type=group.type,
                            exists=child_exists,
                        )
                    )
            for name in template.subscription_children(language):
                sub_key = ("sub", name)
                sub_exists = await self._subscription_child_exists(name) or sub_key in planned
                planned.add(sub_key)
                rows.append(
                    TemplatePreviewRow(
                        label=f"{subs_label} → {name}",
                        type=CategoryType.EXPENSE,
                        exists=sub_exists,
                    )
                )
        return TemplatePreviewResult(keys=[s.key for s in selections], rows=rows)

    # ── Apply ─────────────────────────────────────────────────────────────

    async def apply(
        self, selections: builtins.list[TemplateSelection], *, language: str = "pl"
    ) -> TemplateApplyResult:
        """Create the missing categories of *selections*. Idempotent by blind index."""
        created = 0
        for selection in selections:
            template = self.get(selection.key)
            suffix = self._suffix(template, selection)
            for group in template.groups:
                parent, made = await self._ensure_root(group.parent_name(language) + suffix, group)
                created += made
                for child in group.child_names(language):
                    created += await self._ensure_child(parent, child, group.type)
            subs = template.subscription_children(language)
            if subs:
                created += await self._ensure_subscription_children(subs, language)
        if created:
            await self.session.commit()
        return TemplateApplyResult(keys=[s.key for s in selections], created=created)

    # ── Matching helpers ──────────────────────────────────────────────────

    async def _find_root_id(self, name: str, type: CategoryType) -> int | None:
        result = await self.session.execute(
            select(Category.id).where(
                Category.parent_id.is_(None),
                Category.type == type,
                Category.name_bidx == exact_index(name),
            )
        )
        return result.scalars().first()

    async def _find_child_id(self, parent_id: int, name: str) -> int | None:
        result = await self.session.execute(
            select(Category.id).where(
                Category.parent_id == parent_id,
                Category.name_bidx == exact_index(name),
            )
        )
        return result.scalars().first()

    async def _ensure_root(self, name: str, group: TemplateGroup) -> tuple[Category, int]:
        existing_id = await self._find_root_id(name, group.type)
        if existing_id is not None:
            parent = await self.session.get(Category, existing_id)
            if parent is None:  # vanished between the id lookup and the fetch
                raise NotFoundError(f"Category {existing_id} disappeared while applying a template")
            return parent, 0
        parent = Category(name=name, type=group.type)
        self.session.add(parent)
        await self.session.flush()  # need the id for children and later lookups
        return parent, 1

    async def _ensure_child(self, parent: Category, name: str, type: CategoryType) -> int:
        if await self._find_child_id(parent.id, name) is not None:
            return 0
        self.session.add(Category(name=name, type=type, parent_id=parent.id))
        await self.session.flush()
        return 1

    async def _subscription_child_exists(self, name: str) -> bool:
        categories = CategoryService(self.session)
        root = await categories.get_subscriptions_root()
        if root is None:
            return False
        return await self._find_child_id(root.id, name) is not None

    async def _ensure_subscription_children(self, names: builtins.list[str], language: str) -> int:
        """Add business purposes under the Subscriptions tree (Company — ADR-28, #219).

        Creates only a *bare* Subscriptions root if none exists — not the default purpose
        children — so the whole apply stays in one transaction (``ensure_subscriptions_...``
        commits internally) and nothing is seeded that the template did not ask for. The
        tree's own default purpose children are added later, in the family's language, when
        the Subscriptions page first runs ``ensure_subscriptions_root_and_children`` (which
        finds this root by its flag, so no second root appears). The business purposes are
        added in *language*; a caller on a tree already built in another language would mix
        the two — the Slice 2 view passes the family's language to avoid that.
        """
        categories = CategoryService(self.session)
        root = await categories.get_subscriptions_root()
        if root is None:
            root = Category(
                name=self._subscriptions_label(language),
                type=CategoryType.EXPENSE,
                is_subscriptions_root=True,
            )
            self.session.add(root)
            await self.session.flush()
        created = 0
        for name in names:
            if await self._find_child_id(root.id, name) is None:
                self.session.add(Category(name=name, type=CategoryType.EXPENSE, parent_id=root.id))
                await self.session.flush()
                created += 1
        return created
