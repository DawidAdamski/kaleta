from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from kaleta.models.account import Account
from kaleta.schemas.account import AccountCreate, AccountUpdate


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Account]:
        result = await self.session.execute(
            select(Account).options(selectinload(Account.institution)).order_by(Account.name)
        )
        return list(result.scalars().all())

    async def get(self, account_id: int) -> Account | None:
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.institution))
            .where(Account.id == account_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: AccountCreate) -> Account:
        account = Account(**data.model_dump())
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update(self, account_id: int, data: AccountUpdate) -> Account | None:
        account = await self.get(account_id)
        if account is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(account, field, value)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def delete(self, account_id: int) -> bool:
        account = await self.get(account_id)
        if account is None:
            return False
        await self.session.delete(account)
        await self.session.commit()
        return True

    async def find_by_external_number(self, digits: str) -> Account | None:
        """Find account whose ``external_account_number`` ends with the given digit string."""
        result = await self.session.execute(
            select(Account)
            .options(selectinload(Account.institution))
            .where(Account.external_account_number.ilike(f"%{digits}"))
        )
        return result.scalar_one_or_none()

    async def save_external_number(self, account_id: int, number: str) -> None:
        """Persist the last-10-digits of an external account number for auto-matching."""
        account = await self.get(account_id)
        if account is not None:
            account.external_account_number = number[-10:]
            await self.session.commit()

    async def adjust_balance(self, account_id: int, delta: Decimal) -> None:
        account = await self.get(account_id)
        if account is not None:
            account.balance += delta
            await self.session.commit()
