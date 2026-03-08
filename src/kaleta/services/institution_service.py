from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.institution import Institution
from kaleta.schemas.institution import InstitutionCreate, InstitutionUpdate


class InstitutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Institution]:
        result = await self.session.execute(select(Institution).order_by(Institution.name))
        return list(result.scalars().all())

    async def get(self, institution_id: int) -> Institution | None:
        return await self.session.get(Institution, institution_id)

    async def get_with_accounts(self, institution_id: int) -> Institution | None:
        result = await self.session.execute(
            select(Institution)
            .options(selectinload(Institution.accounts))
            .where(Institution.id == institution_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: InstitutionCreate) -> Institution:
        institution = Institution(**data.model_dump())
        self.session.add(institution)
        await self.session.commit()
        await self.session.refresh(institution)
        return institution

    async def update(self, institution_id: int, data: InstitutionUpdate) -> Institution | None:
        institution = await self.get(institution_id)
        if institution is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(institution, field, value)
        await self.session.commit()
        await self.session.refresh(institution)
        return institution

    async def delete(self, institution_id: int) -> bool:
        institution = await self.get(institution_id)
        if institution is None:
            return False
        await self.session.delete(institution)
        await self.session.commit()
        return True
