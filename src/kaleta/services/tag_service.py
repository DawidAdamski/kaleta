from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.tag import Tag
from kaleta.schemas.tag import TagCreate, TagUpdate


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Tag]:
        result = await self.session.execute(select(Tag).order_by(Tag.name))
        return list(result.scalars())

    async def get(self, tag_id: int) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def create(self, data: TagCreate) -> Tag:
        tag = Tag(**data.model_dump())
        self.session.add(tag)
        await self.session.commit()
        return tag

    async def update(self, tag_id: int, data: TagUpdate) -> Tag | None:
        tag = await self.session.get(Tag, tag_id)
        if tag is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tag, field, value)
        await self.session.commit()
        return tag

    async def delete(self, tag_id: int) -> bool:
        tag = await self.session.get(Tag, tag_id)
        if tag is None:
            return False
        await self.session.delete(tag)
        await self.session.commit()
        return True
