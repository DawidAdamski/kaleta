from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kaleta.models.asset import Asset
from kaleta.schemas.asset import AssetCreate, AssetUpdate


class AssetService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Asset]:
        result = await self.session.execute(select(Asset).order_by(Asset.name))
        return list(result.scalars().all())

    async def get(self, asset_id: int) -> Asset | None:
        result = await self.session.execute(select(Asset).where(Asset.id == asset_id))
        return result.scalar_one_or_none()

    async def create(self, data: AssetCreate) -> Asset:
        asset = Asset(**data.model_dump())
        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def update(self, asset_id: int, data: AssetUpdate) -> Asset | None:
        asset = await self.get(asset_id)
        if asset is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(asset, field, value)
        await self.session.commit()
        await self.session.refresh(asset)
        return asset

    async def delete(self, asset_id: int) -> bool:
        asset = await self.get(asset_id)
        if asset is None:
            return False
        await self.session.delete(asset)
        await self.session.commit()
        return True
