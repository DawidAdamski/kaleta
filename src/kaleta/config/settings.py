# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_KEY = "change-me-in-production"
_DEFAULT_BACKUP_DIR = "~/.kaleta/backups"
_DEFAULT_DATA_DIR = Path.home() / ".kaleta"
_DEFAULT_DB_PATH = _DEFAULT_DATA_DIR / "kaleta.db"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}"


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

    db_url: str = _DEFAULT_DB_URL
    host: str = "127.0.0.1"
    port: int = 8080
    mode: str = "web"  # web | app | api
    secret_key: str = _INSECURE_KEY
    debug: bool = False
    api_token: str | None = None
    session_ttl_hours: int = 72
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retain: int = 7
    backup_dir: str = _DEFAULT_BACKUP_DIR

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

    @field_validator("backup_interval_hours")
    @classmethod
    def _validate_backup_interval(cls, value: int) -> int:
        if value < 1:
            raise ValueError("KALETA_BACKUP_INTERVAL_HOURS must be >= 1")
        return value

    @field_validator("backup_retain")
    @classmethod
    def _validate_backup_retain(cls, value: int) -> int:
        if value < 1:
            raise ValueError("KALETA_BACKUP_RETAIN must be >= 1")
        return value

    @field_validator("session_ttl_hours")
    @classmethod
    def _validate_session_ttl(cls, value: int) -> int:
        if value < 0:
            raise ValueError("KALETA_SESSION_TTL_HOURS must be >= 0 (0 disables expiry)")
        return value

    @field_validator("backup_dir")
    @classmethod
    def _expand_backup_dir(cls, value: str) -> str:
        return str(Path(value).expanduser())

    @model_validator(mode="after")
    def _validate_secret_and_data_dir(self) -> "Settings":
        if not self.debug and self.secret_key == _INSECURE_KEY:
            raise ValueError(
                "KALETA_SECRET_KEY must be set to a secure value in production. "
                "Set KALETA_DEBUG=true to bypass this check in development."
            )
        _DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return self


settings = Settings()
