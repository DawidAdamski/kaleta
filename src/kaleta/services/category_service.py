from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.category import Category, CategoryType
from kaleta.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, type: CategoryType | None = None) -> list[Category]:
        """Return all categories (flat), children eagerly loaded."""
        stmt = select(Category).options(selectinload(Category.children)).order_by(Category.name)
        if type is not None:
            stmt = stmt.where(Category.type == type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_roots(self, type: CategoryType | None = None) -> list[Category]:
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
        return list(result.scalars().all())

    async def get(self, category_id: int) -> Category | None:
        result = await self.session.execute(
            select(Category)
            .options(selectinload(Category.children))
            .where(Category.id == category_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: CategoryCreate) -> Category:
        category = Category(**data.model_dump())
        self.session.add(category)
        await self.session.commit()
        # Re-fetch with eager-loaded children so the response serializer never
        # hits a lazy relationship outside of an async context.
        fetched = await self.get(category.id)
        assert fetched is not None
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
