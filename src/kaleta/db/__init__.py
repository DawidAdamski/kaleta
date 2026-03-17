from kaleta.db import audit as _audit  # noqa: F401 — registers session event listeners
from kaleta.db.base import Base, engine
from kaleta.db.session import AsyncSessionFactory, get_session

__all__ = ["Base", "engine", "AsyncSessionFactory", "get_session", "configure_database"]


def configure_database(db_url: str, debug: bool = False) -> None:
    """Reconfigure the shared session proxy to use a different database URL.

    Safe to call at any point — existing importers share the same proxy object
    and will automatically use the new connection on their next request.
    """
    AsyncSessionFactory.configure(db_url, debug=debug)
