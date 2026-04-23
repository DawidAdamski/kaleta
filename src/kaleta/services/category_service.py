from __future__ import annotations

import builtins
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryUpdate

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data" / "category_templates"


@dataclass(slots=True)
class TemplatePreview:
    key: str
    to_add_income: builtins.list[str]
    to_add_expense: builtins.list[str]
    skipped_income: builtins.list[str]
    skipped_expense: builtins.list[str]

    @property
    def total_to_add(self) -> int:
        return len(self.to_add_income) + len(self.to_add_expense)


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, type: CategoryType | None = None) -> builtins.list[Category]:
        """Return all categories (flat), children eagerly loaded."""
        stmt = select(Category).options(selectinload(Category.children)).order_by(Category.name)
        if type is not None:
            stmt = stmt.where(Category.type == type)
        result = await self.session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def list_roots(self, type: CategoryType | None = None) -> builtins.list[Category]:
        """Return only top-level categories with children eagerly loaded."""
        stmt = (
            select(Category)
            .options(selectinload(Category.children))
            .where(Category.parent_id.is_(None))
            .order_by(Category.name)
        )
        if type is not None:
            stmt = stmt.where(Category.type == type)
        result = await self.session.execute(stmt)
        return builtins.list(result.scalars().all())

    async def get(self, category_id: int) -> Category | None:
        result = await self.session.execute(
            select(Category)
            .options(selectinload(Category.children))
            .where(Category.id == category_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: CategoryCreate) -> Category:
        # SQLite treats NULL != NULL in unique constraints, so enforce (name, parent_id)
        # uniqueness manually to catch duplicate root-level category names.
        stmt = select(Category).where(Category.name == data.name)
        if data.parent_id is None:
            stmt = stmt.where(Category.parent_id.is_(None))
        else:
            stmt = stmt.where(Category.parent_id == data.parent_id)
        existing = await self.session.execute(stmt)
        if existing.scalar_one_or_none() is not None:
            raise IntegrityError(
                statement=None,
                params=None,
                orig=Exception(f"Category name '{data.name}' already exists under the same parent"),
            )
        category = Category(**data.model_dump())
        self.session.add(category)
        await self.session.commit()
        # Re-fetch with eager-loaded children so the response serializer never
        # hits a lazy relationship outside of an async context.
        fetched = await self.get(category.id)
        if fetched is None:
            raise RuntimeError(f"Category id={category.id} not found after commit")
        return fetched

    async def update(self, category_id: int, data: CategoryUpdate) -> Category | None:
        category = await self.get(category_id)
        if category is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        await self.session.commit()
        # Re-fetch with selectinload so children are available for serialization.
        return await self.get(category_id)

    async def delete(self, category_id: int) -> bool:
        category = await self.get(category_id)
        if category is None:
            return False
        await self.session.delete(category)
        await self.session.commit()
        return True

    # ── Subscriptions-tree helpers ────────────────────────────────────────

    async def get_subscriptions_root(self) -> Category | None:
        """Return the single root category flagged as the Subscriptions tree."""
        result = await self.session.execute(
            select(Category)
            .options(selectinload(Category.children))
            .where(Category.is_subscriptions_root.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_subscription_children(self) -> builtins.list[Category]:
        """Direct children of the Subscriptions root, ordered by name.

        Returns an empty list if the root doesn't exist yet.
        """
        root = await self.get_subscriptions_root()
        if root is None:
            return []
        result = await self.session.execute(
            select(Category)
            .where(Category.parent_id == root.id)
            .order_by(Category.name)
        )
        return builtins.list(result.scalars().all())

    async def subscription_category_ids(self) -> set[int]:
        """Return the id set: root + every direct child. Used as a membership test."""
        root = await self.get_subscriptions_root()
        if root is None:
            return set()
        ids = {root.id}
        result = await self.session.execute(
            select(Category.id).where(Category.parent_id == root.id)
        )
        ids.update(result.scalars().all())
        return ids

    async def ensure_subscriptions_root_and_children(
        self, child_names: builtins.list[str] | None = None
    ) -> Category:
        """Create the Subscriptions root + default children if missing.

        Idempotent — safe to call from seeds. Returns the root.
        """
        root = await self.get_subscriptions_root()
        if root is None:
            root = Category(
                name="Subscriptions",
                type=CategoryType.EXPENSE,
                is_subscriptions_root=True,
            )
            self.session.add(root)
            await self.session.commit()
            await self.session.refresh(root)
        defaults = child_names if child_names is not None else ["Monthly", "Yearly", "Other"]
        existing = await self.list_subscription_children()
        existing_names = {c.name for c in existing}
        for name in defaults:
            if name not in existing_names:
                self.session.add(
                    Category(
                        name=name, type=CategoryType.EXPENSE, parent_id=root.id
                    )
                )
        await self.session.commit()
        return await self.get(root.id)  # type: ignore[return-value]

    @staticmethod
    def list_templates() -> builtins.list[str]:
        """Return available template keys (JSON filenames without extension)."""
        if not _TEMPLATE_DIR.is_dir():
            return []
        return sorted(p.stem for p in _TEMPLATE_DIR.glob("*.json"))

    @staticmethod
    def _load_template(key: str) -> dict[str, builtins.list[str]]:
        path = _TEMPLATE_DIR / f"{key}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Category template not found: {key}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "income": [str(n) for n in data.get("income", [])],
            "expense": [str(n) for n in data.get("expense", [])],
        }

    async def preview_template(self, key: str) -> TemplatePreview:
        """Return the diff between a template and the current category set.

        Names collide by (lower-case name, type) scoped to root level.
        """
        tmpl = self._load_template(key)
        existing = await self.list()
        existing_income = {
            c.name.lower()
            for c in existing
            if c.type == CategoryType.INCOME and c.parent_id is None
        }
        existing_expense = {
            c.name.lower()
            for c in existing
            if c.type == CategoryType.EXPENSE and c.parent_id is None
        }

        to_add_income = [n for n in tmpl["income"] if n.lower() not in existing_income]
        to_add_expense = [n for n in tmpl["expense"] if n.lower() not in existing_expense]
        skipped_income = [n for n in tmpl["income"] if n.lower() in existing_income]
        skipped_expense = [n for n in tmpl["expense"] if n.lower() in existing_expense]

        return TemplatePreview(
            key=key,
            to_add_income=to_add_income,
            to_add_expense=to_add_expense,
            skipped_income=skipped_income,
            skipped_expense=skipped_expense,
        )

    async def apply_template(self, key: str) -> int:
        """Insert any missing template entries as root-level categories.

        Returns the number of categories created.
        """
        preview = await self.preview_template(key)
        created = 0
        for name in preview.to_add_income:
            self.session.add(Category(name=name, type=CategoryType.INCOME))
            created += 1
        for name in preview.to_add_expense:
            self.session.add(Category(name=name, type=CategoryType.EXPENSE))
            created += 1
        if created:
            await self.session.commit()
        return created
