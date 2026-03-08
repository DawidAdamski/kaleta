from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from kaleta.config import settings


class Base(DeclarativeBase):
    pass


def create_engine() -> AsyncEngine:
    connect_args = {"check_same_thread": False} if "sqlite" in settings.db_url else {}
    return create_async_engine(
        settings.db_url,
        echo=settings.debug,
        connect_args=connect_args,
    )


engine: AsyncEngine = create_engine()
