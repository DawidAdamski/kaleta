# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.db.types import exact_index
from kaleta.exceptions import ConflictError, ValidationError
from kaleta.models.tag import Tag
from kaleta.schemas.tag import TagCreate, TagUpdate
from kaleta.services.text_order import by_name


class TagService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Tag]:
        result = await self.session.execute(select(Tag))
        return by_name(result.scalars())

    async def get(self, tag_id: int) -> Tag | None:
        return await self.session.get(Tag, tag_id)

    async def _checked_name(self, name: str | None, *, own_id: int | None = None) -> str:
        """A tag's name, stripped: never blank and not another tag's (exact match).

        The exact match is the one ``uq_tags_name_bidx`` enforces, so a clash is
        a 409 here instead of an ``IntegrityError`` at commit.
        """
        cleaned = (name or "").strip()
        if not cleaned:
            raise ValidationError("A tag needs a name.")
        stmt = select(Tag.id).where(Tag.name_bidx == exact_index(cleaned))
        if own_id is not None:
            stmt = stmt.where(Tag.id != own_id)
        if (await self.session.execute(stmt)).first() is not None:
            raise ConflictError(f"A tag named '{cleaned}' already exists")
        return cleaned

    async def create(self, data: TagCreate) -> Tag:
        values = data.model_dump()
        values["name"] = await self._checked_name(data.name)
        tag = Tag(**values)
        self.session.add(tag)
        await self.session.commit()
        return tag

    async def update(self, tag_id: int, data: TagUpdate) -> Tag | None:
        tag = await self.session.get(Tag, tag_id)
        if tag is None:
            return None
        values = data.model_dump(exclude_unset=True)
        if "name" in values:
            values["name"] = await self._checked_name(values["name"], own_id=tag_id)
        for field, value in values.items():
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
