# SPDX-License-Identifier: AGPL-3.0-or-later
import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_KEY = "change-me-in-production"


def normalize_db_url(url: str) -> str:
    """Rewrite driverless SQLAlchemy URLs to their async equivalents."""
    scheme, _, remainder = url.partition("://")
    if "+" in scheme or "://" not in url:
        return url

    if scheme == "sqlite":
        return f"sqlite+aiosqlite://{remainder}"
    if scheme == "postgresql":
        return f"postgresql+asyncpg://{remainder}"
    if scheme == "postgres":
        return f"postgresql+asyncpg://{remainder}"
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KALETA_", env_file=".env", extra="ignore")

    db_url: str = "sqlite+aiosqlite:///kaleta.db"
    host: str = "127.0.0.1"
    port: int = 8080
    mode: str = "web"  # web | app | api
    secret_key: str = _INSECURE_KEY
    debug: bool = False
    api_token: str | None = None

    @field_validator("db_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: str) -> str:
        normalized = normalize_db_url(value)
        if normalized != value:
            logger.info(
                "KALETA_DB_URL rewritten from %r to %r for async SQLAlchemy",
                value,
                normalized,
            )
        return normalized

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if not self.debug and self.secret_key == _INSECURE_KEY:
            raise ValueError(
                "KALETA_SECRET_KEY must be set to a secure value in production. "
                "Set KALETA_DEBUG=true to bypass this check in development."
            )
        return self


settings = Settings()
