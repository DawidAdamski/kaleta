# SPDX-License-Identifier: AGPL-3.0-or-later
import logging
from pathlib import Path
from typing import Literal

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
    #: Hours without a request after which a UI session ends, however young it
    #: is (``0`` disables). Never longer than ``session_ttl_hours``.
    session_idle_hours: int = 12
    #: Mark the session cookie ``Secure``. The browser then never sends it over
    #: plain http, so on an http-only install login silently stops working —
    #: turn it on only behind TLS (a hosted deployment or a TLS reverse proxy).
    session_cookie_secure: bool = False
    #: ``strict`` drops the cookie on every navigation that starts outside the
    #: app, e-mail confirmation links included; ``lax`` is the safe default.
    session_cookie_samesite: Literal["lax", "strict"] = "lax"
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    backup_retain: int = 7
    backup_dir: str = _DEFAULT_BACKUP_DIR
    demo: bool = False
    events_enabled: bool = True
    event_retention_days: int = 7
    log_format: str = "text"  # text | json
    log_level: str = "INFO"
    bug_reports_enabled: bool = True
    bug_report_retention_days: int = 90
    bug_report_webhook: str | None = None
    bug_report_webhook_include_logs: bool = False
    bug_report_email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True
    error_tracker_dsn: str | None = None

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

    @field_validator("session_idle_hours")
    @classmethod
    def _validate_session_idle(cls, value: int) -> int:
        if value < 0:
            raise ValueError("KALETA_SESSION_IDLE_HOURS must be >= 0 (0 disables idle expiry)")
        return value

    @model_validator(mode="after")
    def _cap_session_idle(self) -> "Settings":
        # An idle window longer than the absolute TTL can never fire; the
        # config only says the same limit twice, so cap it rather than refuse
        # to start.
        ttl = self.session_ttl_hours
        if ttl > 0 and self.session_idle_hours > ttl:
            logger.warning(
                "KALETA_SESSION_IDLE_HOURS=%d exceeds KALETA_SESSION_TTL_HOURS=%d; capping to %d",
                self.session_idle_hours,
                ttl,
                ttl,
            )
            self.session_idle_hours = ttl
        return self

    @field_validator("session_cookie_samesite", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("backup_dir")
    @classmethod
    def _expand_backup_dir(cls, value: str) -> str:
        return str(Path(value).expanduser())

    @field_validator("event_retention_days")
    @classmethod
    def _validate_event_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("KALETA_EVENT_RETENTION_DAYS must be >= 1")
        return value

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"text", "json"}:
            raise ValueError("KALETA_LOG_FORMAT must be 'text' or 'json'")
        return normalized

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in logging.getLevelNamesMapping():
            raise ValueError("KALETA_LOG_LEVEL must be a Python logging level name")
        return normalized

    @field_validator("bug_report_retention_days")
    @classmethod
    def _validate_bug_report_retention(cls, value: int) -> int:
        if value < 1:
            raise ValueError("KALETA_BUG_REPORT_RETENTION_DAYS must be >= 1")
        return value

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
